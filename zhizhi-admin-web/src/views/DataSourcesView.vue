<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { CirclePlus, Refresh as RotateCcw, Search } from "@element-plus/icons-vue";
import FormDrawer from "@/components/FormDrawer.vue";
import ManagementEmptyState from "@/components/ManagementEmptyState.vue";
import { RESOURCE_PAGE_SIZE } from "@/utils/pagination";
import { useAuthStore } from "@/stores/auth";
import { useScopeStore } from "@/stores/scope";
import { scopeKey, scopeBreadcrumb } from "@/utils/scope";
import type { AdminScopeRef } from "@/types/admin";
import type { DataSourceBinding, DataSourceResource, DataSourceScope, DataSourceWrite } from "@/types/dataSources";
import { deleteDataSource, deleteDataSourceBinding, grantDataSource, listAssignableDataSources, listDataSourceBindings, listDataSources, revokeDataSource, saveDataSource, saveDataSourceBinding, testDataSource } from "@/api/dataSources";

const props = withDefaults(defineProps<{ mode?: "global" | "tenant" }>(), { mode: "tenant" });
const PAGE_SIZE = RESOURCE_PAGE_SIZE;
const auth = useAuthStore();
const scopes = useScopeStore();
const tab = ref(props.mode === "global" ? "resources" : "availability");
const sources = ref<DataSourceResource[]>([]);
const sourceCache = reactive(new Map<string, DataSourceResource>());
const total = ref(0);
const page = ref(1);
const search = ref("");
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const drawer = ref<"source" | "grant" | "binding" | null>(null);
const editing = ref<DataSourceResource | null>(null);
const binding = ref<DataSourceBinding | null>(null);
const candidates = ref<DataSourceResource[]>([]);
const candidatePage = ref(1);
const candidateTotal = ref(0);
const candidateSearch = ref("");
const chosenGrants = ref<string[]>([]);
const boundIds = ref<string[]>([]);
const defaultId = ref("");
const bindingStatus = ref<"active" | "inactive">("active");
const scopeOptions = computed(() => scopes.nodes.filter(node => node.scope.scope_tenant_id === scopes.currentTenantId));
const scope = computed<DataSourceScope>(() => ({ tenant_id: scopes.selectedScope?.scope_tenant_id ?? "", organization_unit_id: scopes.selectedScope?.scope_organization_unit_id ?? "" }));

function contains(grant: AdminScopeRef, target: AdminScopeRef, strict: boolean): boolean {
  if (grant.scope_tenant_id !== target.scope_tenant_id) return false;
  if (grant.scope_type === "tenant") return !strict || target.scope_type !== "tenant";
  const id = grant.scope_organization_unit_id;
  return (target.scope_organization_path ?? []).some(unit => unit.id === id)
    && (!strict || id !== target.scope_organization_unit_id);
}
function allowed(code: string, parent = false): boolean {
  if (auth.isSuper) return true;
  const target = scopes.selectedScope;
  if (!target) return false;
  return auth.tenantMembers.some(member => member.status === "active"
    && member.roles.some(role => role.role?.status !== "inactive" && role.permissions?.some(permission => permission.permission_code === code && permission.status !== "inactive"))
    && member.scopes.some(item => {
      const granted = item.scope ?? { scope_type: item.scope_type!, scope_tenant_id: item.scope_tenant_id ?? "", scope_organization_unit_id: item.scope_organization_unit_id ?? "" };
      return contains(granted, target, parent);
    }));
}
const canGrant = computed(() => allowed("data_sources.entitlements.edit", true));
const canBind = computed(() => allowed("data_sources.bindings.edit"));
const sourceTab = computed(() => props.mode === "global" && tab.value === "resources");
const title = computed(() => drawer.value === "source" ? (editing.value ? "编辑数据源" : "新建数据源") : drawer.value === "grant" ? "分配数据源" : "配置运行数据源");
const defaults = (): DataSourceWrite => ({ source_key: "", tag: "", display_name: "", description: "", driver: "mysql", status: "active", host: "", port: 3306, database: "", username: "", server_id: "main", endpoint_url: "http://127.0.0.1:8002/mcp", pool_size: 3, pool_timeout_seconds: 5, connect_timeout_seconds: 5, query_timeout_seconds: 30, max_rows: 500, max_result_bytes: 262144, allowed_schemas: [], tls: false });
const form = reactive<DataSourceWrite>(defaults());
const password = ref("");
const schemas = ref("");
let refreshVersion = 0;
function remember(items: DataSourceResource[]): void { items.forEach(item => sourceCache.set(item.id, item)); }
function label(id: string): string { const item = sourceCache.get(id); return item ? `${item.display_name || item.source_key} · ${item.tag}` : "已绑定数据源"; }
function selectScope(key: string): void { scopes.setSelectedScope(scopeOptions.value.find(node => scopeKey(node.scope) === key)?.scope ?? null); }

async function refresh(): Promise<void> {
  const version = ++refreshVersion;
  if (!sourceTab.value && !scope.value.tenant_id) { sources.value = []; total.value = 0; binding.value = null; return; }
  loading.value = true; error.value = "";
  try {
    const query = { page: page.value, page_size: PAGE_SIZE, search: search.value, ...(sourceTab.value ? {} : scope.value) };
    const result = await listDataSources(query);
    const lastPage = Math.max(1, Math.ceil(result.pagination.total / PAGE_SIZE));
    if (page.value > lastPage) { page.value = lastPage; await refresh(); return; }
    const nextBinding = sourceTab.value ? null : (await listDataSourceBindings({ tenant_id: query.tenant_id ?? "", organization_unit_id: query.organization_unit_id ?? "" })).items[0] ?? null;
    if (version !== refreshVersion) return;
    sources.value = result.items; total.value = result.pagination.total; remember(result.items);
    binding.value = nextBinding;
    if (binding.value?.sources) remember(binding.value.sources);
  } catch (cause) { error.value = cause instanceof Error ? cause.message : "加载数据源失败。"; }
  finally { loading.value = false; }
}
function resetSearch(): void { search.value = ""; page.value = 1; void refresh(); }
function openSource(item?: DataSourceResource): void {
  editing.value = item ?? null;
  Object.assign(form, defaults(), item ?? {});
  password.value = ""; schemas.value = item?.allowed_schemas?.join(", ") ?? "";
  drawer.value = "source";
}
async function loadCandidates(): Promise<void> {
  try {
    const result = drawer.value === "grant"
      ? await listAssignableDataSources(scope.value, candidatePage.value, candidateSearch.value)
      : await listDataSources({ ...scope.value, page: candidatePage.value, page_size: 50, search: candidateSearch.value });
    candidates.value = result.items.filter(item => item.status === "active");
    candidateTotal.value = result.pagination.total; remember(result.items);
  } catch (cause) { ElMessage.error(cause instanceof Error ? cause.message : "加载候选资源失败。"); }
}
async function openResources(kind: "grant" | "binding"): Promise<void> {
  drawer.value = kind; candidatePage.value = 1; candidateSearch.value = ""; chosenGrants.value = [];
  boundIds.value = [...(binding.value?.source_ids ?? [])]; defaultId.value = binding.value?.default_source_id ?? ""; bindingStatus.value = binding.value?.status ?? "active";
  await loadCandidates();
}
async function submit(): Promise<void> {
  const submittedScope = { ...scope.value };
  saving.value = true;
  try {
    if (drawer.value === "source") {
      const values = Object.fromEntries(Object.keys(defaults()).map(key => [key, form[key as keyof DataSourceWrite]])) as unknown as DataSourceWrite;
      values.tag = values.tag.trim().toUpperCase();
      if (editing.value?.revision) values.revision = editing.value.revision;
      values.allowed_schemas = schemas.value.split(",").map(value => value.trim()).filter(Boolean);
      if (password.value) values.password = password.value;
      if (!editing.value && !password.value) throw new Error("请输入数据库密码。");
      await saveDataSource(values, editing.value?.id);
    } else if (drawer.value === "grant") {
      if (!chosenGrants.value.length) throw new Error("请选择要分配的数据源。");
      for (const id of chosenGrants.value) await grantDataSource(submittedScope, id);
    } else {
      if (!boundIds.value.includes(defaultId.value)) throw new Error("请从已绑定数据源中选择默认源。");
      await saveDataSourceBinding({ ...submittedScope, source_ids: boundIds.value, default_source_id: defaultId.value, status: bindingStatus.value });
    }
    drawer.value = null; password.value = ""; ElMessage.success("已保存。"); await refresh();
  } catch (cause) { ElMessage.error(cause instanceof Error ? cause.message : "保存失败。"); }
  finally { saving.value = false; }
}
async function remove(item: DataSourceResource): Promise<void> {
  try {
    await ElMessageBox.confirm(sourceTab.value ? "删除前必须解除全部授权和绑定。" : "撤销前必须解除本级绑定及下级授权。", sourceTab.value ? "删除数据源" : "撤销可用资源", { type: "warning" });
    if (sourceTab.value) await deleteDataSource(item.id); else await revokeDataSource(scope.value, item.id);
    await refresh();
  } catch (cause) { if (cause instanceof Error) ElMessage.error(cause.message); }
}
async function unbind(): Promise<void> {
  try { await ElMessageBox.confirm("解除本级绑定后，将按最近上级有效绑定解析数据源。", "解除绑定"); await deleteDataSourceBinding(scope.value); await refresh(); }
  catch (cause) { if (cause instanceof Error) ElMessage.error(cause.message); }
}
async function probe(item: DataSourceResource): Promise<void> {
  try { const result = await testDataSource(item.id); if (result.success) ElMessage.success(result.message); else ElMessage.error(result.message); await refresh(); }
  catch (cause) { ElMessage.error(cause instanceof Error ? cause.message : "连接测试失败。"); }
}
watch(() => form.driver, (value, old) => { if (!editing.value && value !== old) form.port = value === "postgresql" ? 5432 : 3306; });
watch(() => sourceTab.value ? "global" : `${tab.value}:${scope.value.tenant_id}:${scope.value.organization_unit_id}`, () => { page.value = 1; drawer.value = null; sourceCache.clear(); void refresh(); });
watch(boundIds, ids => { if (!ids.includes(defaultId.value)) defaultId.value = ""; });
onMounted(async () => { if (props.mode === "tenant" && !scopes.nodes.length) await scopes.fetchCatalog(); await refresh(); });
</script>

<template>
  <section class="data-sources-page" :class="{ 'is-global-mode': props.mode === 'global' }">
    <header v-if="props.mode === 'tenant'" class="source-header">
      <div><h2>数据源管理</h2><p>管理当前租户和组织的数据源授权与运行配置</p></div>
    </header>
    <el-tabs v-if="props.mode === 'tenant'" v-model="tab" class="source-tabs">
      <el-tab-pane label="数据源授权" name="availability" />
      <el-tab-pane label="运行数据源" name="bindings" />
    </el-tabs>
    <div v-if="!sourceTab" class="scope-toolbar">
      <span>当前作用域</span>
      <el-select :model-value="scopes.selectedScope ? scopeKey(scopes.selectedScope) : ''" filterable @update:model-value="selectScope">
        <el-option v-for="node in scopeOptions" :key="scopeKey(node.scope)" :value="scopeKey(node.scope)" :label="scopeBreadcrumb(node.scope, scopes.nodes).join(' / ')" />
      </el-select>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
    <template v-if="tab !== 'bindings'">
      <div class="resource-toolbar global-resource-toolbar">
        <h2 class="global-resource-title">{{ sourceTab ? '数据源配置' : '数据源授权' }}</h2>
        <div class="source-tools global-resource-tools">
        <div class="global-resource-filters">
        <el-input v-model="search" :prefix-icon="Search" clearable placeholder="搜索编号、名称或标签" @keyup.enter="page = 1; refresh()" />
        <el-button :icon="RotateCcw" :disabled="loading" @click="resetSearch">重置</el-button>
        <el-button :icon="Search" type="primary" :disabled="loading" @click="page = 1; refresh()">搜索</el-button>
        </div>
        <div class="global-resource-actions">
        <el-button v-if="sourceTab && auth.isSuper" type="primary" :icon="CirclePlus" @click="openSource()">新建数据源</el-button>
        <el-button v-else-if="canGrant" type="primary" :icon="CirclePlus" @click="openResources('grant')">分配数据源</el-button>
        </div>
        </div>
      </div>
      <div class="admin-table-region source-table-region global-resource-table-region">
      <el-table v-loading="loading" :data="sources" height="100%" row-key="id" class="admin-data-table global-resource-table">
        <el-table-column label="数据源" min-width="190"><template #default="{ row }"><strong>{{ row.display_name || row.source_key }}</strong><div class="muted">{{ row.source_key }}</div></template></el-table-column>
        <el-table-column prop="tag" label="逻辑标签" width="120" />
        <el-table-column prop="driver" label="数据库类型" width="130" />
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column v-if="sourceTab" label="连接" min-width="190"><template #default="{ row }">{{ row.host }}:{{ row.port }} / {{ row.database }}</template></el-table-column>
        <el-table-column v-if="sourceTab" label="测试状态" width="110"><template #default="{ row }">{{ row.last_test_status === 'success' ? '成功' : row.last_test_status === 'failed' ? '失败' : '未测试' }}</template></el-table-column>
        <el-table-column label="操作" :width="sourceTab ? 230 : 110" align="right" fixed="right"><template #default="{ row }">
          <div class="global-resource-row-actions">
          <template v-if="sourceTab"><el-button link type="primary" @click="openSource(row)">编辑</el-button><el-button link type="primary" @click="probe(row)">测试连接</el-button></template>
          <el-button v-if="sourceTab || canGrant" link type="danger" @click="remove(row)">{{ sourceTab ? '删除' : '撤销授权' }}</el-button>
          </div>
        </template></el-table-column>
        <template #empty>
          <ManagementEmptyState
            v-if="sourceTab"
            :title="search.trim() ? '未找到匹配的数据源' : '暂无数据源配置'"
            :description="search.trim() ? '请调整搜索条件后重试。' : '登记数据库并测试连接，再到数据源管理配置授权与运行数据源。'"
          >
            <el-button v-if="!search.trim() && auth.isSuper" type="primary" @click="openSource()">创建第一个数据源</el-button>
          </ManagementEmptyState>
          <span v-else>当前范围没有数据源资源</span>
        </template>
      </el-table>
      </div>
      <el-pagination v-if="total > 0" v-model:current-page="page" class="admin-pagination" :page-size="PAGE_SIZE" :total="total" layout="total, prev, pager, next" @current-change="refresh" />
    </template>
    <div v-else class="binding-panel">
      <div class="resource-toolbar"><h3>本级运行数据源</h3><el-button v-if="canBind" type="primary" @click="openResources('binding')">{{ binding ? '编辑运行数据源' : '配置运行数据源' }}</el-button><el-button v-if="binding && canBind" type="danger" plain @click="unbind">清除本级配置</el-button></div>
      <el-alert v-if="!binding" title="本级未配置运行数据源，将使用最近上级满足授权的配置。" type="info" :closable="false" />
      <template v-else><p>状态：{{ binding.status === 'active' ? '启用' : '停用' }} · 默认数据源：{{ label(binding.default_source_id) }}</p><el-tag v-for="id in binding.source_ids" :key="id" class="source-chip">{{ label(id) }}{{ id === binding.default_source_id ? '（默认）' : '' }}</el-tag></template>
      <p class="muted">模型依据 Wiki 表字典中的标签选择绑定源；未指定标签时使用默认源，指定标签不可用时不自动换源。</p>
    </div>
    <FormDrawer :open="drawer !== null" :class="{ 'global-resource-form-dialog': props.mode === 'global' }" :placement="props.mode === 'global' ? 'modal' : 'drawer'" :title="title" :saving="saving" :size="props.mode === 'global' ? 'default' : 'wide'" @close="drawer = null; password = ''" @submit="submit">
      <template v-if="drawer === 'source'">
        <h3>资源信息</h3><div class="form-grid">
          <label>资源编号<el-input v-model="form.source_key" :disabled="editing !== null" placeholder="orders-primary" /></label>
          <label>显示名称<el-input v-model="form.display_name" /></label>
          <label>数据源标签<el-input v-model="form.tag" placeholder="OB、ADB 或自定义标签" /></label>
          <label>状态<el-select v-model="form.status"><el-option value="active" label="启用" /><el-option value="inactive" label="停用" /></el-select></label>
        </div><label>说明<el-input v-model="form.description" type="textarea" /></label>
        <h3>数据库连接</h3><div class="form-grid">
          <label>类型<el-select v-model="form.driver"><el-option value="mysql" label="MySQL" /><el-option value="postgresql" label="PostgreSQL" /></el-select></label>
          <label>地址<el-input v-model="form.host" /></label>
          <label>端口<el-input-number v-model="form.port" :min="1" :max="65535" /></label>
          <label>数据库<el-input v-model="form.database" /></label>
          <label>只读账号<el-input v-model="form.username" /></label>
          <label>{{ editing ? '新密码（留空保持原密码）' : '密码' }}<el-input v-model="password" type="password" autocomplete="new-password" show-password /></label>
          <label>允许的 Schema / 数据库<el-input v-model="schemas" placeholder="逗号分隔；留空使用该数据库的默认范围" /></label>
          <label>TLS<el-switch v-model="form.tls" /></label>
        </div>
        <h3>查询服务</h3><div class="form-grid"><label>服务编号<el-input v-model="form.server_id" /></label><label>MCP 地址<el-input v-model="form.endpoint_url" /></label></div>
        <h3>连接与查询限制</h3><div class="form-grid">
          <label>单源最大连接数<el-input-number v-model="form.pool_size" :min="1" :max="32" /></label>
          <label>等待连接超时（秒）<el-input-number v-model="form.pool_timeout_seconds" :min="1" :max="60" /></label>
          <label>建立连接超时（秒）<el-input-number v-model="form.connect_timeout_seconds" :min="1" :max="60" /></label>
          <label>查询超时（秒）<el-input-number v-model="form.query_timeout_seconds" :min="1" :max="300" /></label>
          <label>最多返回行数<el-input-number v-model="form.max_rows" :min="1" :max="10000" /></label>
          <label>结果大小上限（字节）<el-input-number v-model="form.max_result_bytes" :min="2048" :max="1048576" /></label>
        </div><p class="muted">连接按需建立，空闲时回收。账号必须具有只读权限；修改连接参数或密码后，新请求使用新配置。</p>
      </template>
      <template v-else>
        <div class="resource-toolbar"><el-input v-model="candidateSearch" placeholder="搜索候选资源" @keyup.enter="candidatePage = 1; loadCandidates()" /><el-button @click="candidatePage = 1; loadCandidates()">搜索</el-button></div>
        <el-checkbox-group v-if="drawer === 'grant'" v-model="chosenGrants"><div v-for="item in candidates" :key="item.id" class="candidate"><el-checkbox :value="item.id">{{ item.display_name || item.source_key }} · {{ item.tag }}</el-checkbox></div></el-checkbox-group>
        <el-checkbox-group v-else v-model="boundIds" :max="32"><div v-for="item in candidates" :key="item.id" class="candidate"><el-checkbox :value="item.id">{{ item.display_name || item.source_key }} · {{ item.tag }}</el-checkbox></div></el-checkbox-group>
        <el-pagination v-model:current-page="candidatePage" class="admin-pagination" :page-size="50" :total="candidateTotal" layout="total, prev, pager, next" @current-change="loadCandidates" />
        <template v-if="drawer === 'binding'"><label>默认数据源<el-select v-model="defaultId" placeholder="从已选数据源中指定默认源"><el-option v-for="id in boundIds" :key="id" :value="id" :label="label(id)" /></el-select></label><label>状态<el-select v-model="bindingStatus"><el-option value="active" label="启用" /><el-option value="inactive" label="停用" /></el-select></label><p class="muted">同一绑定集合中的标签必须唯一。绑定集合整体继承，不与上级集合合并。</p></template>
      </template>
    </FormDrawer>
  </section>
</template>

<style scoped>
.data-sources-page { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; background: white; overflow: hidden; }
.source-header, .resource-toolbar, .scope-toolbar { display: flex; align-items: center; gap: 12px; }
.source-header { flex: 0 0 auto; padding: 14px 24px; border-bottom: 1px solid rgba(219, 222, 234, 0.92); }
.source-header h2 { font-size: 18px; }
.resource-toolbar { flex: 0 0 auto; min-height: 3.75rem; padding: 0.75rem 1.25rem; border-bottom: 1px solid rgba(219, 222, 234, 0.92); }
.resource-toolbar h2 { margin: 0; white-space: nowrap; }
.source-tools { display: flex; flex: 1; justify-content: flex-end; align-items: center; gap: 0.625rem; }
.source-tools > .el-input { width: 240px; }
.source-tools > .global-resource-filters, .source-tools > .global-resource-actions { display: flex; align-items: center; gap: 0.625rem; }
.source-tools .global-resource-filters > .el-input { width: 240px; }
.scope-toolbar { flex: 0 0 auto; padding: 0.75rem 1.25rem; border-bottom: 1px solid rgba(219, 222, 234, 0.92); }
.source-tabs { flex: 0 0 auto; padding: 0 1.25rem; }
.source-tabs :deep(.el-tabs__header) { margin: 0; }
.source-table-region { display: flex; flex: 1 1 auto; min-height: 0; overflow: hidden; }
h2 { font-size: 0.9375rem; font-weight: 700; } h3 { font-size: 16px; font-weight: 650; }
.source-header p, .muted { color: #64748b; font-size: 13px; margin-top: 5px; }
.resource-toolbar > .el-input { max-width: 320px; } .scope-toolbar .el-select { min-width: 320px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin: 14px 0 22px; }
label { display: flex; flex-direction: column; gap: 8px; font-size: 13px; } label .el-input-number { width: 100%; }
.candidate { padding: 10px 0; border-bottom: 1px solid #eef2f7; } .source-chip { margin: 10px 10px 10px 0; }
.binding-panel { display: flex; flex: 1; min-height: 0; overflow: auto; flex-direction: column; gap: 16px; padding: 0 1.25rem; }
@media (max-width: 760px) { .form-grid { grid-template-columns: 1fr; } .resource-toolbar, .source-tools, .source-tools > .global-resource-filters { flex-wrap: wrap; } .source-tools > .el-input, .source-tools .global-resource-filters > .el-input { width: 100%; } }
</style>
