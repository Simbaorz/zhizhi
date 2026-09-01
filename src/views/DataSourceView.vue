<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { CirclePlus, Coin, Delete, EditPen, Link, Refresh, Tickets } from "@element-plus/icons-vue";

import {
  createDataSource,
  createDataSourceBinding,
  createDataSourceEntitlement,
  deleteDataSource,
  deleteDataSourceBinding,
  deleteDataSourceEntitlement,
  listDataSourceBindingPage,
  listDataSourceEntitlements,
  listDataSources,
  listOrganizationUnits,
  listOrgTenants,
  updateDataSource,
  updateDataSourceBinding,
  updateDataSourceEntitlement,
} from "@/api/admin";
import { ApiError } from "@/api/http";
import AppPanel from "@/components/AppPanel.vue";
import { useScopeStore } from "@/stores/scope";
import type {
  DataSourceScopeType,
  ManagedDataSource,
  ManagedDataSourceBinding,
  ManagedDataSourceEntitlement,
  ManagedOrganizationUnit,
  ManagedTenant,
} from "@/types/admin";

const props = withDefaults(defineProps<{ mode?: "global" | "tenant" }>(), { mode: "tenant" });
type ActiveTab = "sources" | "availability" | "bindings";
type DrawerMode = "source-create" | "source-edit" | "availability-create" | "binding-create" | "binding-edit";

const scopeStore = useScopeStore();
const activeTab = ref<ActiveTab>(props.mode === "global" ? "sources" : "availability");
const loading = ref(false);
const saving = ref(false);
const tenants = ref<ManagedTenant[]>([]);
const units = ref<ManagedOrganizationUnit[]>([]);
const sources = ref<ManagedDataSource[]>([]);
const entitlements = ref<ManagedDataSourceEntitlement[]>([]);
const bindings = ref<ManagedDataSourceBinding[]>([]);
const tenantId = ref("");
const drawerMode = ref<DrawerMode | null>(null);
const selectedSource = ref<ManagedDataSource | null>(null);
const selectedBinding = ref<ManagedDataSourceBinding | null>(null);

const scopeForm = reactive({ scopeType: "tenant" as DataSourceScopeType, organizationUnitId: "" });
const resourceForm = reactive({ sourceIds: [] as string[], sourceId: "", status: "active" });
const sourceForm = reactive({
  sourceKey: "", displayName: "", description: "", status: "active", apiUrl: "",
  appId: "", appKey: "", appSecret: "", defaultDatabaseKey: "", execSourcesCode: "",
  timeoutSeconds: 30, defaultMaxRows: 50, hardMaxRows: 500, allowDatabases: "", logSql: false,
});

const currentTenant = computed(() => tenants.value.find((item) => item.id === tenantId.value));
const unitMap = computed(() => new Map(units.value.map((unit) => [unit.id, unit])));
const sourceMap = computed(() => new Map(sources.value.map((source) => [source.id, source])));
const availableSourceIds = computed(() => new Set(entitlements.value.filter((item) => item.status === "active").map((item) => item.data_source_id)));
const drawerTitle = computed(() => ({
  "source-create": "新建数据源", "source-edit": "编辑数据源",
  "availability-create": "分配可用数据源", "binding-create": "绑定默认数据源",
  "binding-edit": "修改默认数据源",
})[drawerMode.value ?? "source-create"]);

async function loadAll(): Promise<void> {
  loading.value = true;
  try {
    [tenants.value, sources.value] = await Promise.all([
      listOrgTenants(), listDataSources({ pageSize: 100 }),
    ]);
    const preferred = props.mode === "tenant" ? scopeStore.currentTenantId : tenantId.value;
    tenantId.value = tenants.value.some((item) => item.id === preferred) ? preferred : tenants.value[0]?.id ?? "";
    await loadTenantResources();
  } catch (error) { notifyError(error, "加载数据源管理数据失败"); }
  finally { loading.value = false; }
}

async function loadTenantResources(): Promise<void> {
  if (!tenantId.value) { units.value = []; entitlements.value = []; bindings.value = []; return; }
  try {
    const [organizationUnits, available, selected] = await Promise.all([
      listOrganizationUnits(tenantId.value),
      listDataSourceEntitlements(tenantId.value, { pageSize: 100 }),
      listDataSourceBindingPage(tenantId.value, { pageSize: 100 }),
    ]);
    units.value = organizationUnits; entitlements.value = available.items; bindings.value = selected.items;
  } catch (error) { notifyError(error, "加载租户数据源分配失败"); }
}

function openCreateSource(): void {
  selectedSource.value = null;
  Object.assign(sourceForm, {
    sourceKey: "", displayName: "", description: "", status: "active", apiUrl: "",
    appId: "", appKey: "", appSecret: "", defaultDatabaseKey: "", execSourcesCode: "",
    timeoutSeconds: 30, defaultMaxRows: 50, hardMaxRows: 500, allowDatabases: "", logSql: false,
  });
  drawerMode.value = "source-create";
}

function openEditSource(source: ManagedDataSource): void {
  selectedSource.value = source;
  Object.assign(sourceForm, {
    sourceKey: source.source_key, displayName: source.display_name, description: source.description,
    status: source.status, apiUrl: source.api_url, appId: source.app_id, appKey: "", appSecret: "",
    defaultDatabaseKey: source.default_database_key, execSourcesCode: source.exec_sources_code,
    timeoutSeconds: source.timeout_seconds, defaultMaxRows: source.default_max_rows,
    hardMaxRows: source.hard_max_rows, allowDatabases: source.allow_databases, logSql: source.log_sql,
  });
  drawerMode.value = "source-edit";
}

function openAvailability(): void {
  resetScope(); resourceForm.sourceIds = []; resourceForm.status = "active";
  drawerMode.value = "availability-create";
}

function openBinding(binding?: ManagedDataSourceBinding): void {
  selectedBinding.value = binding ?? null;
  scopeForm.scopeType = binding?.scope_type ?? "tenant";
  scopeForm.organizationUnitId = binding?.organization_unit_id ?? "";
  resourceForm.sourceId = binding?.data_source_id ?? "";
  resourceForm.status = binding?.status ?? "active";
  drawerMode.value = binding ? "binding-edit" : "binding-create";
}

async function saveDrawer(): Promise<void> {
  if (!drawerMode.value || saving.value) return;
  saving.value = true;
  try {
    if (drawerMode.value === "source-create") {
      validateSource(true); await createDataSource({ ...sourceForm });
      sources.value = await listDataSources({ pageSize: 100 });
    } else if (drawerMode.value === "source-edit" && selectedSource.value) {
      validateSource(false);
      await updateDataSource(selectedSource.value.id, {
        displayName: sourceForm.displayName.trim(), description: sourceForm.description.trim(),
        status: sourceForm.status, apiUrl: sourceForm.apiUrl.trim(), appId: sourceForm.appId.trim(),
        appKey: sourceForm.appKey || undefined, appSecret: sourceForm.appSecret || undefined,
        defaultDatabaseKey: sourceForm.defaultDatabaseKey.trim(), execSourcesCode: sourceForm.execSourcesCode.trim(),
        timeoutSeconds: sourceForm.timeoutSeconds, defaultMaxRows: sourceForm.defaultMaxRows,
        hardMaxRows: sourceForm.hardMaxRows, allowDatabases: sourceForm.allowDatabases.trim(), logSql: sourceForm.logSql,
      });
      sources.value = await listDataSources({ pageSize: 100 });
    } else if (drawerMode.value === "availability-create") {
      validateScope(); if (!resourceForm.sourceIds.length) throw new Error("请选择至少一个数据源");
      await createDataSourceEntitlement({
        tenantId: tenantId.value, scopeType: scopeForm.scopeType,
        organizationUnitId: scopeForm.organizationUnitId, dataSourceIds: resourceForm.sourceIds,
        status: resourceForm.status,
      });
      await loadTenantResources();
    } else if (drawerMode.value === "binding-create") {
      validateScope(); if (!resourceForm.sourceId) throw new Error("请选择默认数据源");
      await createDataSourceBinding({
        tenantId: tenantId.value, scopeType: scopeForm.scopeType,
        organizationUnitId: scopeForm.organizationUnitId, dataSourceId: resourceForm.sourceId,
        status: resourceForm.status,
      });
      await loadTenantResources();
    } else if (selectedBinding.value) {
      await updateDataSourceBinding(selectedBinding.value.id, { status: resourceForm.status });
      await loadTenantResources();
    }
    drawerMode.value = null; ElMessage.success("保存成功");
  } catch (error) { notifyError(error, "保存失败"); }
  finally { saving.value = false; }
}

function validateSource(requireCredentials: boolean): void {
  if (!sourceForm.sourceKey.trim() || !sourceForm.apiUrl.trim() || !sourceForm.appId.trim()
    || !sourceForm.defaultDatabaseKey.trim() || !sourceForm.execSourcesCode.trim()) {
    throw new Error("请填写数据源标识、API 地址、App ID、默认数据库与执行源编码");
  }
  if (requireCredentials && (!sourceForm.appKey || !sourceForm.appSecret)) throw new Error("请填写 App Key 与 App Secret");
  if (sourceForm.defaultMaxRows > sourceForm.hardMaxRows) throw new Error("默认行数不能超过最大行数");
}

function validateScope(): void {
  if (!tenantId.value) throw new Error("请选择租户");
  if (scopeForm.scopeType === "organization_unit" && !scopeForm.organizationUnitId) throw new Error("请选择组织单元");
}
function resetScope(): void { scopeForm.scopeType = "tenant"; scopeForm.organizationUnitId = ""; }

async function removeSource(source: ManagedDataSource): Promise<void> {
  await confirmDelete(source.display_name || source.source_key);
  try { await deleteDataSource(source.id); sources.value = await listDataSources({ pageSize: 100 }); }
  catch (error) { notifyError(error, "删除数据源失败"); }
}
async function toggleEntitlement(item: ManagedDataSourceEntitlement): Promise<void> {
  try { await updateDataSourceEntitlement(item.id, { status: item.status === "active" ? "inactive" : "active" }); await loadTenantResources(); }
  catch (error) { notifyError(error, "更新可用状态失败"); }
}
async function removeEntitlement(item: ManagedDataSourceEntitlement): Promise<void> {
  await confirmDelete(sourceName(item.data_source_id));
  try { await deleteDataSourceEntitlement(item.id); await loadTenantResources(); }
  catch (error) { notifyError(error, "删除可用数据源失败"); }
}
async function removeBinding(item: ManagedDataSourceBinding): Promise<void> {
  await confirmDelete(scopeLabel(item.scope_type, item.organization_unit_id));
  try { await deleteDataSourceBinding(item.id); await loadTenantResources(); }
  catch (error) { notifyError(error, "删除绑定失败"); }
}
async function confirmDelete(label: string): Promise<void> {
  await ElMessageBox.confirm(`确定删除“${label}”吗？`, "删除确认", { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" });
}

function sourceName(id: string): string { const source = sourceMap.value.get(id); return source?.display_name || source?.source_key || id; }
function scopeLabel(type: DataSourceScopeType, unitId: string): string {
  if (type === "tenant") return currentTenant.value?.tenant_name || "租户级";
  const path: string[] = []; let current = unitMap.value.get(unitId); const seen = new Set<string>();
  while (current && !seen.has(current.id)) { seen.add(current.id); path.unshift(current.name || current.external_key); current = current.parent_id ? unitMap.value.get(current.parent_id) : undefined; }
  return path.join(" / ") || unitId;
}
function notifyError(error: unknown, fallback: string): void { ElMessage.error(error instanceof ApiError || error instanceof Error ? error.message : fallback); }

watch(tenantId, loadTenantResources);
watch(() => scopeForm.scopeType, (value) => { if (value === "tenant") scopeForm.organizationUnitId = ""; });
onMounted(loadAll);
</script>

<template>
  <div class="resource-page" v-loading="loading">
    <AppPanel class="resource-hero">
      <div class="resource-title"><span class="resource-icon"><el-icon><Coin /></el-icon></span><div><span class="eyebrow">DATA ACCESS</span><h1>数据源管理</h1><p>将企业实时数据能力配置为受控资源，并按组织作用域分配和绑定。</p></div></div>
      <div class="hero-actions"><el-select v-if="activeTab !== 'sources'" v-model="tenantId" class="tenant-select"><el-option v-for="tenant in tenants" :key="tenant.id" :label="tenant.tenant_name || tenant.tenant_code" :value="tenant.id" /></el-select><el-button :icon="Refresh" circle @click="loadAll" /></div>
    </AppPanel>
    <div class="resource-tabs">
      <button v-if="mode === 'global'" :class="{ active: activeTab === 'sources' }" @click="activeTab = 'sources'"><el-icon><Coin /></el-icon>数据源配置</button>
      <button :class="{ active: activeTab === 'availability' }" @click="activeTab = 'availability'"><el-icon><Tickets /></el-icon>可用数据源</button>
      <button :class="{ active: activeTab === 'bindings' }" @click="activeTab = 'bindings'"><el-icon><Link /></el-icon>默认绑定</button>
    </div>
    <AppPanel class="table-card">
      <div class="table-head"><div><strong>{{ activeTab === 'sources' ? '全局数据源配置' : activeTab === 'availability' ? '组织可用数据源' : '组织默认数据源' }}</strong><small v-if="activeTab !== 'sources'">{{ currentTenant?.tenant_name || '未选择租户' }}</small></div><el-button v-if="activeTab === 'sources'" type="primary" :icon="CirclePlus" @click="openCreateSource">新建数据源</el-button><el-button v-else-if="activeTab === 'availability'" type="primary" :icon="CirclePlus" :disabled="!tenantId" @click="openAvailability">分配数据源</el-button><el-button v-else type="primary" :icon="CirclePlus" :disabled="!tenantId" @click="openBinding()">新增绑定</el-button></div>
      <el-table v-if="activeTab === 'sources'" :data="sources">
        <el-table-column label="数据源" min-width="220"><template #default="{ row }"><div class="primary-cell"><span>{{ row.display_name || row.source_key }}</span><small>{{ row.source_key }}</small></div></template></el-table-column>
        <el-table-column prop="api_url" label="API 地址" min-width="260" show-overflow-tooltip /><el-table-column prop="default_database_key" label="默认数据库" min-width="140" /><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'primary' : 'info'">{{ row.status === 'active' ? '启用' : '停用' }}</el-tag></template></el-table-column><el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><el-button link type="primary" :icon="EditPen" @click="openEditSource(row)">编辑</el-button><el-button link type="danger" :icon="Delete" @click="removeSource(row)">删除</el-button></template></el-table-column>
      </el-table>
      <el-table v-else-if="activeTab === 'availability'" :data="entitlements"><el-table-column label="作用域" min-width="240"><template #default="{ row }"><div class="primary-cell"><span>{{ scopeLabel(row.scope_type, row.organization_unit_id) }}</span><small>{{ row.scope_type === 'tenant' ? '租户' : '组织单元' }}</small></div></template></el-table-column><el-table-column label="可用数据源" min-width="220"><template #default="{ row }">{{ sourceName(row.data_source_id) }}</template></el-table-column><el-table-column label="状态" width="110"><template #default="{ row }"><el-switch :model-value="row.status === 'active'" @change="toggleEntitlement(row)" /></template></el-table-column><el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="danger" :icon="Delete" @click="removeEntitlement(row)">删除</el-button></template></el-table-column></el-table>
      <el-table v-else :data="bindings"><el-table-column label="作用域" min-width="240"><template #default="{ row }"><div class="primary-cell"><span>{{ scopeLabel(row.scope_type, row.organization_unit_id) }}</span><small>运行时从最深层向租户逐级回溯</small></div></template></el-table-column><el-table-column label="默认数据源" min-width="220"><template #default="{ row }">{{ sourceName(row.data_source_id) }}</template></el-table-column><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'primary' : 'info'">{{ row.status === 'active' ? '启用' : '停用' }}</el-tag></template></el-table-column><el-table-column label="操作" width="150"><template #default="{ row }"><el-button link type="primary" :icon="EditPen" @click="openBinding(row)">编辑</el-button><el-button link type="danger" :icon="Delete" @click="removeBinding(row)">删除</el-button></template></el-table-column></el-table>
    </AppPanel>

    <el-drawer v-model="drawerMode" :title="drawerTitle" size="520px" destroy-on-close>
      <el-form v-if="drawerMode?.startsWith('source')" label-position="top">
        <div class="form-grid"><el-form-item label="数据源标识" required><el-input v-model="sourceForm.sourceKey" :disabled="drawerMode === 'source-edit'" /></el-form-item><el-form-item label="显示名称"><el-input v-model="sourceForm.displayName" /></el-form-item></div>
        <el-form-item label="说明"><el-input v-model="sourceForm.description" type="textarea" /></el-form-item><el-form-item label="查询 API 地址" required><el-input v-model="sourceForm.apiUrl" /></el-form-item>
        <div class="form-grid"><el-form-item label="App ID" required><el-input v-model="sourceForm.appId" /></el-form-item><el-form-item label="执行源编码" required><el-input v-model="sourceForm.execSourcesCode" /></el-form-item></div>
        <div class="form-grid"><el-form-item :label="drawerMode === 'source-edit' ? 'App Key（留空不修改）' : 'App Key'" required><el-input v-model="sourceForm.appKey" show-password /></el-form-item><el-form-item :label="drawerMode === 'source-edit' ? 'App Secret（留空不修改）' : 'App Secret'" required><el-input v-model="sourceForm.appSecret" show-password /></el-form-item></div>
        <el-form-item label="默认数据库" required><el-input v-model="sourceForm.defaultDatabaseKey" /></el-form-item><el-form-item label="允许数据库"><el-input v-model="sourceForm.allowDatabases" placeholder="逗号分隔；留空表示使用服务端策略" /></el-form-item>
        <div class="form-grid"><el-form-item label="默认最大行数"><el-input-number v-model="sourceForm.defaultMaxRows" :min="1" /></el-form-item><el-form-item label="硬性最大行数"><el-input-number v-model="sourceForm.hardMaxRows" :min="1" /></el-form-item></div>
        <el-form-item><el-checkbox v-model="sourceForm.logSql">记录 SQL 审计日志</el-checkbox></el-form-item>
      </el-form>
      <el-form v-else label-position="top"><el-form-item label="作用域"><el-radio-group v-model="scopeForm.scopeType" :disabled="drawerMode === 'binding-edit'"><el-radio-button value="tenant">租户</el-radio-button><el-radio-button value="organization_unit">组织单元</el-radio-button></el-radio-group></el-form-item><el-form-item v-if="scopeForm.scopeType === 'organization_unit'" label="组织单元" required><el-select v-model="scopeForm.organizationUnitId" filterable :disabled="drawerMode === 'binding-edit'"><el-option v-for="unit in units" :key="unit.id" :label="scopeLabel('organization_unit', unit.id)" :value="unit.id" /></el-select></el-form-item><el-form-item v-if="drawerMode === 'availability-create'" label="可用数据源" required><el-select v-model="resourceForm.sourceIds" multiple filterable><el-option v-for="source in sources" :key="source.id" :label="source.display_name || source.source_key" :value="source.id" /></el-select></el-form-item><el-form-item v-else label="默认数据源" required><el-select v-model="resourceForm.sourceId" filterable :disabled="drawerMode === 'binding-edit'"><el-option v-for="source in sources" :key="source.id" :label="source.display_name || source.source_key" :value="source.id" :disabled="!availableSourceIds.has(source.id) && drawerMode === 'binding-create'" /></el-select><small class="form-hint">绑定的数据源必须已分配为可用资源。</small></el-form-item><el-form-item label="状态"><el-radio-group v-model="resourceForm.status"><el-radio-button value="active">启用</el-radio-button><el-radio-button value="inactive">停用</el-radio-button></el-radio-group></el-form-item></el-form>
      <template #footer><el-button @click="drawerMode = null">取消</el-button><el-button type="primary" :loading="saving" @click="saveDrawer">保存</el-button></template>
    </el-drawer>
  </div>
</template>

<style scoped>
.resource-page { display: grid; gap: 18px; }.resource-hero { display: flex; align-items: center; justify-content: space-between; padding: 22px 26px; background: linear-gradient(118deg, #fff 58%, #eeebff); }.resource-title,.hero-actions,.table-head,.resource-tabs { display: flex; align-items: center; gap: 14px; }.resource-icon { display: grid; width: 48px; height: 48px; place-items: center; border-radius: 14px; background: linear-gradient(135deg,#4f46e5,#8b5cf6); color:#fff; font-size:22px; }.eyebrow { color:#6366f1; font-size:10px; font-weight:800; letter-spacing:.15em; }h1 { margin:3px 0; color:#24213e; font-size:22px; }.resource-title p { margin:0; color:#818197; }.tenant-select { width:220px; }.resource-tabs { gap:4px; padding:4px; width:max-content; border:1px solid #e1def0; border-radius:13px; background:#fff; }.resource-tabs button { display:flex; align-items:center; gap:7px; padding:9px 15px; border:0; border-radius:9px; background:transparent; color:#77758d; cursor:pointer; }.resource-tabs button.active { background:#eeecff; color:#4f46e5; font-weight:700; }.table-card { padding:0; overflow:hidden; }.table-head { justify-content:space-between; padding:18px 20px; border-bottom:1px solid #ebe9f3; }.table-head strong,.table-head small,.primary-cell span,.primary-cell small { display:block; }.table-head small,.primary-cell small,.form-hint { margin-top:3px; color:#8b899e; font-size:11px; }.primary-cell span { color:#2e2c48; font-weight:700; }.form-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }@media(max-width:760px){.resource-hero,.table-head{align-items:flex-start;flex-direction:column}.hero-actions,.tenant-select{width:100%}.form-grid{grid-template-columns:1fr}}
</style>
