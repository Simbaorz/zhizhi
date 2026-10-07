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
const candidateLoading = ref(false);
const candidateError = ref("");
const selectedScopeKey = ref("");
const formScopeKey = ref("");
const chosenGrants = ref<string[]>([]);
const boundIds = ref<string[]>([]);
const defaultId = ref("");
const bindingStatus = ref<"active" | "inactive">("active");
const scopeOptions = computed(() => scopes.nodes.filter(node => node.scope.scope_tenant_id === scopes.currentTenantId));
const selectedScope = computed(() => scopeOptions.value.find(node => scopeKey(node.scope) === selectedScopeKey.value)?.scope ?? null);
const scope = computed<DataSourceScope>(() => sourceScope(selectedScope.value));
const formScope = computed<DataSourceScope>(() => sourceScope(scopeOptions.value.find(node => scopeKey(node.scope) === formScopeKey.value)?.scope ?? null));
function sourceScope(value: AdminScopeRef | null): DataSourceScope {
  return { tenant_id: value?.scope_tenant_id ?? "", organization_unit_id: value?.scope_organization_unit_id ?? "" };
}
function scopeLabel(value: AdminScopeRef): string {
  return value.scope_type === "tenant" ? "租户范围" : scopeBreadcrumb(value, scopes.nodes).slice(1).join(" / ");
}
const selectedScopeLabel = computed(() => selectedScope.value ? scopeLabel(selectedScope.value) : "未选择范围");

function contains(grant: AdminScopeRef, target: AdminScopeRef, strict: boolean): boolean {
  if (grant.scope_tenant_id !== target.scope_tenant_id) return false;
  if (grant.scope_type === "tenant") return !strict || target.scope_type !== "tenant";
  const id = grant.scope_organization_unit_id;
  return (target.scope_organization_path ?? []).some(unit => unit.id === id)
    && (!strict || id !== target.scope_organization_unit_id);
}
function allowed(code: string, parent = false, target = selectedScope.value): boolean {
  if (auth.isSuper) return true;
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
const editableScopeOptions = computed(() => scopeOptions.value.filter(node => allowed(drawer.value === "grant" ? "data_sources.entitlements.edit" : "data_sources.bindings.edit", drawer.value === "grant", node.scope)));
const sourceTab = computed(() => props.mode === "global" && tab.value === "resources");
const title = computed(() => drawer.value === "source" ? (editing.value ? "编辑数据源" : "新建数据源") : drawer.value === "grant" ? "分配数据源" : "配置运行数据源");
const defaults = (): DataSourceWrite => ({ source_key: "", tag: "", display_name: "", description: "", driver: "mysql", status: "active", host: "", port: 3306, database: "", username: "", server_id: "main", endpoint_url: "http://127.0.0.1:8002/mcp", pool_size: 3, pool_timeout_seconds: 5, connect_timeout_seconds: 5, query_timeout_seconds: 30, max_rows: 500, max_result_bytes: 262144, allowed_schemas: [], tls: false });
const form = reactive<DataSourceWrite>(defaults());
const password = ref("");
const schemas = ref("");
let refreshVersion = 0;
function remember(items: DataSourceResource[]): void { items.forEach(item => sourceCache.set(item.id, item)); }
function label(id: string): string { const item = sourceCache.get(id); return item ? `${item.display_name || item.source_key} · ${item.tag}` : "已绑定数据源"; }
function syncSelectedScope(): void {
  const preferred = scopes.selectedScope;
  selectedScopeKey.value = scopeKey(scopeOptions.value.find(node => preferred && scopeKey(node.scope) === scopeKey(preferred))?.scope ?? scopeOptions.value[0]?.scope ?? { scope_type: "tenant", scope_tenant_id: "" });
}

async function refresh(): Promise<void> {
  const version = ++refreshVersion;
  if (!sourceTab.value && !scope.value.tenant_id) { sources.value = []; total.value = 0; binding.value = null; loading.value = false; return; }
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
  } catch (cause) { if (version === refreshVersion) { sources.value = []; binding.value = null; total.value = 0; error.value = cause instanceof Error ? cause.message : "加载数据源失败。"; } }
  finally { if (version === refreshVersion) loading.value = false; }
}
function resetSearch(): void { search.value = ""; page.value = 1; void refresh(); }
function openSource(item?: DataSourceResource): void {
  editing.value = item ?? null;
  Object.assign(form, defaults(), item ?? {});
  password.value = ""; schemas.value = item?.allowed_schemas?.join(", ") ?? "";
  drawer.value = "source";
}
let candidateVersion = 0;
async function loadCandidates(): Promise<void> {
  const version = ++candidateVersion;
  const kind = drawer.value;
  candidateLoading.value = true; candidateError.value = "";
  try {
    const result = kind === "grant"
      ? await listAssignableDataSources(formScope.value, candidatePage.value, candidateSearch.value)
      : await listDataSources({ ...formScope.value, page: candidatePage.value, page_size: 50, search: candidateSearch.value });
    if (version !== candidateVersion || kind !== drawer.value) return;
    candidates.value = result.items.filter(item => item.status === "active");
    candidateTotal.value = result.pagination.total; remember(result.items);
  } catch (cause) { if (version === candidateVersion) { candidates.value = []; candidateTotal.value = 0; candidateError.value = cause instanceof Error ? cause.message : "加载候选资源失败。"; } }
  finally { if (version === candidateVersion) candidateLoading.value = false; }
}
function closeForm(): void { drawer.value = null; password.value = ""; ++candidateVersion; candidateLoading.value = false; }
function removeSelected(id: string): void {
  const selected = drawer.value === "grant" ? chosenGrants : boundIds;
  selected.value = selected.value.filter(value => value !== id);
}
async function changeFormScope(): Promise<void> {
  ++candidateVersion; chosenGrants.value = []; boundIds.value = []; defaultId.value = ""; candidates.value = []; candidateTotal.value = 0; candidatePage.value = 1; candidateSearch.value = "";
  await loadCandidates();
}
async function openResources(kind: "grant" | "binding"): Promise<void> {
  formScopeKey.value = selectedScopeKey.value;
  drawer.value = kind; candidatePage.value = 1; candidateSearch.value = ""; chosenGrants.value = [];
  boundIds.value = [...(binding.value?.source_ids ?? [])]; defaultId.value = binding.value?.default_source_id ?? ""; bindingStatus.value = binding.value?.status ?? "active";
  await loadCandidates();
}
async function submit(): Promise<void> {
  if (saving.value || !drawer.value) return;
  if (drawer.value !== "source" && (candidateLoading.value || candidateError.value)) return;
  const submittedScope = { ...formScope.value };
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
      if (!submittedScope.tenant_id) throw new Error("请选择授权范围。");
      if (!chosenGrants.value.length) throw new Error("请选择要分配的数据源。");
      for (const id of chosenGrants.value) await grantDataSource(submittedScope, id);
    } else {
      if (!submittedScope.tenant_id || !boundIds.value.length) throw new Error("请选择绑定范围和数据源。");
      if (!boundIds.value.includes(defaultId.value)) throw new Error("请从已绑定数据源中选择默认源。");
      await saveDataSourceBinding({ ...submittedScope, source_ids: boundIds.value, default_source_id: defaultId.value, status: bindingStatus.value });
    }
    if (drawer.value !== "source") selectedScopeKey.value = formScopeKey.value;
    closeForm(); ElMessage.success("已保存。"); await refresh();
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
watch(() => sourceTab.value ? "global" : `${tab.value}:${scope.value.tenant_id}:${scope.value.organization_unit_id}`, () => { page.value = 1; closeForm(); void refresh(); });
watch(() => scopes.currentTenantId, () => { sourceCache.clear(); syncSelectedScope(); });
watch(boundIds, ids => { if (!ids.includes(defaultId.value)) defaultId.value = ""; });
onMounted(async () => { if (props.mode === "tenant") { if (!scopes.nodes.length) await scopes.fetchCatalog(); syncSelectedScope(); } await refresh(); });
</script>

<template>
  <section class="data-sources-page admin-management-page" :class="{ 'is-global-mode': props.mode === 'global' }">
    <header v-if="props.mode === 'tenant'" class="source-header">
      <div><h2>数据源管理</h2><p>先分配可用数据源，再配置查询使用的数据源与默认源。</p></div>
    </header>
    <el-alert v-if="error" type="error" :title="error" :closable="false" />
      <div class="resource-toolbar global-resource-toolbar">
        <h2 v-if="sourceTab" class="global-resource-title">数据源配置</h2>
        <nav v-else class="source-management-tabs" aria-label="数据源管理范围">
          <button type="button" :class="{ active: tab === 'availability' }" @click="tab = 'availability'">可用数据源</button>
          <button type="button" :class="{ active: tab === 'bindings' }" @click="tab = 'bindings'">运行数据源</button>
        </nav>
        <div class="source-tools global-resource-tools">
        <div v-if="sourceTab" class="global-resource-filters">
        <el-input v-model="search" :prefix-icon="Search" clearable placeholder="搜索编号、名称或标签" @keyup.enter="page = 1; refresh()" />
        <el-button :icon="RotateCcw" :disabled="loading" @click="resetSearch">重置</el-button>
        <el-button :icon="Search" type="primary" :disabled="loading" @click="page = 1; refresh()">搜索</el-button>
        </div>
        <div class="global-resource-actions">
        <el-button v-if="sourceTab && auth.isSuper" type="primary" :icon="CirclePlus" @click="openSource()">新建数据源</el-button>
        <el-button v-else-if="tab === 'availability' && canGrant" type="primary" :icon="CirclePlus" :disabled="!scope.tenant_id || loading" @click="openResources('grant')">分配数据源</el-button>
        <el-button v-else-if="tab === 'bindings' && canBind" type="primary" :icon="CirclePlus" :disabled="!scope.tenant_id || loading" @click="openResources('binding')">{{ binding ? '编辑绑定' : '绑定数据源' }}</el-button>
        </div>
        </div>
      </div>
      <div v-if="!sourceTab" class="source-filter-toolbar">
        <label class="scope-filter-label">组织范围</label>
        <el-select v-model="selectedScopeKey" filterable aria-label="组织范围" placeholder="选择组织范围">
          <el-option v-for="node in scopeOptions" :key="scopeKey(node.scope)" :value="scopeKey(node.scope)" :label="scopeLabel(node.scope)" />
        </el-select>
        <template v-if="tab === 'availability'">
          <el-input v-model="search" :prefix-icon="Search" clearable placeholder="搜索编号、名称或标签" @keyup.enter="page = 1; refresh()" />
          <el-button :icon="RotateCcw" :disabled="loading" @click="resetSearch">重置</el-button>
          <el-button :icon="Search" type="primary" :disabled="loading" @click="page = 1; refresh()">搜索</el-button>
        </template>
      </div>
      <p v-if="!sourceTab" class="source-list-note">{{ tab === 'availability' ? '将数据源分配到租户或组织后，该范围才能绑定使用；下级分配需先取得上级授权。' : '从该范围的可用数据源中选择查询源，并指定默认源。未配置本级绑定时，运行时向上查找最近的有效配置。' }}</p>
      <div class="admin-table-region source-table-region global-resource-table-region">
      <el-table v-if="tab !== 'bindings'" v-loading="loading" :data="sources" height="100%" row-key="id" class="admin-data-table global-resource-table">
        <el-table-column v-if="!sourceTab" label="授权范围" min-width="200"><template #default>{{ selectedScopeLabel }}</template></el-table-column>
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
          <ManagementEmptyState v-else :title="scope.tenant_id ? '暂无可用数据源' : '请先在顶部选择租户'" :description="search.trim() ? '请调整搜索条件后重试。' : '先从上级可用数据源中分配授权，再到运行数据源中绑定使用。'">
            <el-button v-if="canGrant && scope.tenant_id && !search.trim()" type="primary" @click="openResources('grant')">分配数据源</el-button>
          </ManagementEmptyState>
        </template>
      </el-table>
      <el-table v-else v-loading="loading" :data="binding ? [binding] : []" height="100%" row-key="id" class="admin-data-table global-resource-table">
        <el-table-column label="绑定范围" min-width="200"><template #default>{{ selectedScopeLabel }}</template></el-table-column>
        <el-table-column label="绑定数据源" min-width="260"><template #default="{ row }"><div v-for="id in row.source_ids" :key="id" class="binding-source"><strong>{{ label(id) }}</strong><el-tag v-if="id === row.default_source_id" size="small">默认</el-tag></div></template></el-table-column>
        <el-table-column label="默认数据源" min-width="220"><template #default="{ row }">{{ label(row.default_source_id) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column v-if="canBind" label="操作" width="170" align="right" fixed="right"><template #default><div class="global-resource-row-actions"><el-button link type="primary" @click="openResources('binding')">编辑</el-button><el-button link type="danger" @click="unbind">解除绑定</el-button></div></template></el-table-column>
        <template #empty><ManagementEmptyState :title="scope.tenant_id ? '暂无本级数据源绑定' : '请先在顶部选择租户'" description="先分配可用数据源，再绑定查询源和默认源。本级无配置时，运行时向上查找最近的有效配置。"><el-button v-if="canBind && scope.tenant_id" type="primary" @click="openResources('binding')">绑定数据源</el-button></ManagementEmptyState></template>
      </el-table>
      </div>
      <el-pagination v-if="tab !== 'bindings' && total > 0" v-model:current-page="page" class="admin-pagination" :page-size="PAGE_SIZE" :total="total" layout="total, prev, pager, next" @current-change="refresh" />
    <FormDrawer :open="drawer !== null" class="global-resource-form-dialog" placement="modal" :title="title" :saving="saving" :submit-disabled="drawer !== 'source' && (candidateLoading || !!candidateError || !(drawer === 'grant' ? chosenGrants.length : boundIds.length && defaultId))" @close="closeForm" @submit="submit">
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
        <section class="source-form-section">
          <h3>{{ drawer === 'grant' ? '1. 选择授权范围' : '1. 绑定范围' }}</h3>
          <el-select v-model="formScopeKey" :disabled="saving || drawer === 'binding'" filterable aria-label="表单组织范围" @change="changeFormScope"><el-option v-for="node in editableScopeOptions" :key="scopeKey(node.scope)" :value="scopeKey(node.scope)" :label="scopeLabel(node.scope)" /></el-select>
          <p class="muted">{{ drawer === 'grant' ? '组织只能接收上级已经授权的数据源。' : '从页面工具栏选择组织范围，再配置该范围的运行数据源。' }}</p>
        </section>
        <section class="source-form-section">
          <h3>2. {{ drawer === 'grant' ? '选择要分配的数据源' : '选择查询数据源' }} <span class="muted">已选 {{ drawer === 'grant' ? chosenGrants.length : boundIds.length }} 项</span></h3>
          <div class="candidate-search"><el-input v-model="candidateSearch" :prefix-icon="Search" clearable placeholder="搜索名称、编号或标签" @keyup.enter="candidatePage = 1; loadCandidates()" /><el-button :disabled="candidateLoading" @click="candidatePage = 1; loadCandidates()">搜索</el-button></div>
          <el-alert v-if="candidateError" :title="candidateError" type="error" :closable="false" />
          <el-checkbox-group v-if="drawer === 'grant'" v-model="chosenGrants" v-loading="candidateLoading" class="candidate-list"><div v-for="item in candidates" :key="item.id" class="candidate" :class="{ selected: chosenGrants.includes(item.id) }"><el-checkbox :value="item.id" :disabled="saving || candidateLoading"><strong>{{ item.display_name || item.source_key }}</strong><small>{{ item.source_key }} · {{ item.tag }} · {{ item.driver }}</small></el-checkbox></div></el-checkbox-group>
          <el-checkbox-group v-else v-model="boundIds" :max="32" v-loading="candidateLoading" class="candidate-list"><div v-for="item in candidates" :key="item.id" class="candidate" :class="{ selected: boundIds.includes(item.id) }"><el-checkbox :value="item.id" :disabled="saving || candidateLoading"><strong>{{ item.display_name || item.source_key }}</strong><small>{{ item.source_key }} · {{ item.tag }} · {{ item.driver }}</small></el-checkbox></div></el-checkbox-group>
          <ManagementEmptyState v-if="!candidateLoading && !candidateError && !candidates.length" :title="candidateSearch.trim() ? '未找到匹配的数据源' : '暂无可选数据源'" :description="drawer === 'grant' ? '请先在全局管理登记数据源，或由上级分配到父级组织。' : '请先在可用数据源中为该范围分配授权。'" />
          <el-pagination v-if="candidateTotal > 0" v-model:current-page="candidatePage" class="admin-pagination" :page-size="50" :total="candidateTotal" layout="total, prev, pager, next" @current-change="loadCandidates" />
          <div class="selected-sources"><el-tag v-for="id in (drawer === 'grant' ? chosenGrants : boundIds)" :key="id" :closable="!saving" @close="removeSelected(id)">{{ label(id) }}</el-tag></div>
        </section>
        <section v-if="drawer === 'binding'" class="source-form-section"><h3>3. 默认源与状态</h3><div class="form-grid"><label>默认数据源<el-select v-model="defaultId" placeholder="从已选数据源中指定默认源"><el-option v-for="id in boundIds" :key="id" :value="id" :label="label(id)" /></el-select></label><label>状态<el-select v-model="bindingStatus"><el-option value="active" label="启用" /><el-option value="inactive" label="停用" /></el-select></label></div><p class="muted">模型按 Wiki 表字典中的标签选择源；未指定标签时使用默认源，指定标签不可用时不自动换源。</p></section>
      </template>
    </FormDrawer>
  </section>
</template>

<style scoped>
.data-sources-page { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; background: white; overflow: hidden; }
.source-header, .resource-toolbar { display: flex; align-items: center; gap: 12px; }
.source-header { flex: 0 0 auto; padding: 14px 24px; border-bottom: 1px solid rgba(219, 222, 234, 0.92); }
.source-header h2 { font-size: 18px; }
.resource-toolbar { flex: 0 0 auto; min-height: 3.75rem; padding: 0.75rem 1.25rem; border-bottom: 1px solid rgba(219, 222, 234, 0.92); }
.resource-toolbar h2 { margin: 0; white-space: nowrap; }
.source-tools { display: flex; flex: 1; justify-content: flex-end; align-items: center; gap: 0.625rem; }
.source-tools > .el-input { width: 240px; }
.source-tools > .global-resource-filters, .source-tools > .global-resource-actions { display: flex; align-items: center; gap: 0.625rem; }
.source-tools .global-resource-filters > .el-input { width: 240px; }
.source-table-region { display: flex; flex: 1 1 0; min-height: 0; overflow: hidden; }
h2 { font-size: 0.9375rem; font-weight: 700; } h3 { font-size: 16px; font-weight: 650; }
.source-header p, .muted { color: #64748b; font-size: 13px; margin-top: 5px; }
.resource-toolbar > .el-input { max-width: 320px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin: 14px 0 22px; }
label { display: flex; flex-direction: column; gap: 8px; font-size: 13px; } label .el-input-number { width: 100%; }
.source-management-tabs { display: flex; flex: 0 0 auto; gap: 24px; }
.source-management-tabs button { position: relative; border: 0; padding: 8px 0; background: transparent; color: var(--text-secondary); font-size: 13px; font-weight: 650; white-space: nowrap; }
.source-management-tabs button.active { color: var(--accent); }
.source-management-tabs button.active::after { position: absolute; right: 0; bottom: -12px; left: 0; height: 2px; background: var(--accent); content: ''; }
.source-filter-toolbar { display: flex; flex: 0 0 auto; align-items: center; gap: 8px; padding: 12px 20px; }
.source-filter-toolbar .scope-filter-label { font-size: 13px; white-space: nowrap; }
.source-filter-toolbar .el-select { width: 240px; }
.source-filter-toolbar .el-input { width: 240px; margin-left: auto; }
.source-list-note { flex: 0 0 auto; margin: 0; padding: 0 20px 12px; color: var(--text-secondary); font-size: 12px; line-height: 18px; }
.binding-source { display: flex; align-items: center; gap: 8px; padding: 3px 0; }
.source-form-section { padding-bottom: 20px; }
.source-form-section h3 { margin: 0 0 12px; font-size: 13px; font-weight: 600; }
.source-form-section > .el-select { width: 100%; }
.source-form-section .form-grid { margin: 0; }
.candidate-search { display: flex; gap: 8px; margin-bottom: 12px; }
.candidate-list { max-height: 280px; min-height: 40px; overflow-y: auto; border: 1px solid var(--border-weak); border-radius: 8px; }
.candidate { padding: 12px; border-bottom: 1px solid var(--border-weak); }
.candidate:last-child { border-bottom: 0; }
.candidate.selected { background: var(--el-color-primary-light-9); }
.candidate .el-checkbox { display: flex; flex-direction: row; align-items: center; justify-content: flex-start; height: auto; width: 100%; margin: 0; gap: 0; }
.candidate :deep(.el-checkbox__label) { display: flex; min-width: 0; flex-direction: column; gap: 4px; white-space: normal; }
.candidate strong { font-size: 13px; }
.candidate small { color: var(--text-tertiary); font-size: 12px; }
.selected-sources { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
@media (max-width: 760px) { .form-grid { grid-template-columns: 1fr; } .resource-toolbar, .source-tools, .source-tools > .global-resource-filters { flex-wrap: wrap; } .source-tools > .el-input, .source-tools .global-resource-filters > .el-input { width: 100%; } }
@media (max-width: 680px) { .source-filter-toolbar { flex-wrap: wrap; } .source-filter-toolbar .el-select, .source-filter-toolbar .el-input { width: 100%; margin-left: 0; } }
</style>
