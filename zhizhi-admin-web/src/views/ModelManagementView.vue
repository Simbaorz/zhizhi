<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { CirclePlus, Cpu, Delete, EditPen, Link, Refresh, Tickets } from "@element-plus/icons-vue";

import {
  createLLMBinding,
  createLLMEntitlements,
  createLLMModel,
  deleteLLMBinding,
  deleteLLMEntitlement,
  deleteLLMModel,
  listLLMBindingPage,
  listLLMEntitlements,
  listLLMModels,
  listOrganizationUnits,
  listOrgTenants,
  updateLLMBinding,
  updateLLMEntitlement,
  updateLLMModel,
} from "@/api/admin";
import { ApiError } from "@/api/http";
import AppPanel from "@/components/AppPanel.vue";
import { useScopeStore } from "@/stores/scope";
import type {
  LLMBindingScopeType,
  LLMProtocol,
  LLMProvider,
  ManagedLLMBinding,
  ManagedLLMConfig,
  ManagedLLMEntitlement,
  ManagedOrganizationUnit,
  ManagedTenant,
} from "@/types/admin";

const props = withDefaults(defineProps<{ mode?: "global" | "tenant" }>(), { mode: "tenant" });
type ActiveTab = "models" | "availability" | "bindings";
type DrawerMode = "model-create" | "model-edit" | "availability-create" | "binding-create" | "binding-edit";

const scopeStore = useScopeStore();
const activeTab = ref<ActiveTab>(props.mode === "global" ? "models" : "availability");
const loading = ref(false);
const saving = ref(false);
const tenants = ref<ManagedTenant[]>([]);
const units = ref<ManagedOrganizationUnit[]>([]);
const models = ref<ManagedLLMConfig[]>([]);
const entitlements = ref<ManagedLLMEntitlement[]>([]);
const bindings = ref<ManagedLLMBinding[]>([]);
const tenantId = ref("");
const drawerMode = ref<DrawerMode | null>(null);
const selectedModel = ref<ManagedLLMConfig | null>(null);
const selectedBinding = ref<ManagedLLMBinding | null>(null);

const scopeForm = reactive({
  scopeType: "tenant" as LLMBindingScopeType,
  organizationUnitId: "",
});
const modelForm = reactive({
  alias: "",
  displayName: "",
  provider: "openai" as LLMProvider,
  protocol: "openai-chat" as LLMProtocol,
  modelName: "",
  endpointUrl: "",
  status: "active",
  supportStream: true,
  supportTools: true,
  supportVision: false,
  supportThinking: false,
  timeoutSeconds: 600,
  generationConfigText: "{}",
  providerConfigText: "{}",
  credentialsText: "{}",
});
const resourceForm = reactive({ modelIds: [] as string[], modelId: "", status: "active" });

const drawerTitle = computed(() => ({
  "model-create": "新建模型配置",
  "model-edit": "编辑模型配置",
  "availability-create": "分配可用模型",
  "binding-create": "绑定默认模型",
  "binding-edit": "修改默认模型",
})[drawerMode.value ?? "model-create"]);
const currentTenant = computed(() => tenants.value.find((item) => item.id === tenantId.value));
const unitMap = computed(() => new Map(units.value.map((unit) => [unit.id, unit])));
const modelMap = computed(() => new Map(models.value.map((model) => [model.id, model])));
const availableModelIds = computed(() => new Set(entitlements.value.filter((item) => item.status === "active").map((item) => item.llm_config_id)));

async function loadAll(): Promise<void> {
  loading.value = true;
  try {
    [tenants.value, models.value] = await Promise.all([
      listOrgTenants(),
      listLLMModels({ pageSize: 100 }),
    ]);
    const preferred = props.mode === "tenant" ? scopeStore.currentTenantId : tenantId.value;
    tenantId.value = tenants.value.some((item) => item.id === preferred)
      ? preferred
      : tenants.value[0]?.id ?? "";
    await loadTenantResources();
  } catch (error) {
    notifyError(error, "加载模型管理数据失败");
  } finally {
    loading.value = false;
  }
}

async function loadTenantResources(): Promise<void> {
  if (!tenantId.value) {
    units.value = [];
    entitlements.value = [];
    bindings.value = [];
    return;
  }
  try {
    const [organizationUnits, available, selected] = await Promise.all([
      listOrganizationUnits(tenantId.value),
      listLLMEntitlements(tenantId.value, { pageSize: 100 }),
      listLLMBindingPage(tenantId.value, { pageSize: 100 }),
    ]);
    units.value = organizationUnits;
    entitlements.value = available.items;
    bindings.value = selected.items;
  } catch (error) {
    notifyError(error, "加载租户模型分配失败");
  }
}

function openCreateModel(): void {
  selectedModel.value = null;
  Object.assign(modelForm, {
    alias: "", displayName: "", provider: "openai", protocol: "openai-chat",
    modelName: "", endpointUrl: "", status: "active", supportStream: true,
    supportTools: true, supportVision: false, supportThinking: false,
    timeoutSeconds: 600, generationConfigText: "{}", providerConfigText: "{}",
    credentialsText: "{}",
  });
  drawerMode.value = "model-create";
}

function openEditModel(model: ManagedLLMConfig): void {
  selectedModel.value = model;
  Object.assign(modelForm, {
    alias: model.alias,
    displayName: model.display_name,
    provider: model.provider,
    protocol: model.protocol,
    modelName: model.model_name,
    endpointUrl: model.endpoint_url,
    status: model.status,
    supportStream: model.support_stream,
    supportTools: model.support_tools,
    supportVision: model.support_vision,
    supportThinking: model.support_thinking,
    timeoutSeconds: model.timeout_seconds,
    generationConfigText: JSON.stringify(model.generation_config ?? {}, null, 2),
    providerConfigText: JSON.stringify(model.provider_config ?? {}, null, 2),
    credentialsText: "{}",
  });
  drawerMode.value = "model-edit";
}

function openAvailability(): void {
  resetScopeForm();
  resourceForm.modelIds = [];
  resourceForm.status = "active";
  drawerMode.value = "availability-create";
}

function openBinding(binding?: ManagedLLMBinding): void {
  selectedBinding.value = binding ?? null;
  scopeForm.scopeType = binding?.scope_type ?? "tenant";
  scopeForm.organizationUnitId = binding?.organization_unit_id ?? "";
  resourceForm.modelId = binding?.llm_config_id ?? "";
  resourceForm.status = binding?.status ?? "active";
  drawerMode.value = binding ? "binding-edit" : "binding-create";
}

async function saveDrawer(): Promise<void> {
  if (!drawerMode.value || saving.value) return;
  saving.value = true;
  try {
    if (drawerMode.value === "model-create") {
      await createLLMModel(modelPayload());
      models.value = await listLLMModels({ pageSize: 100 });
    } else if (drawerMode.value === "model-edit" && selectedModel.value) {
      const payload = modelPayload();
      await updateLLMModel(selectedModel.value.id, payload);
      models.value = await listLLMModels({ pageSize: 100 });
    } else if (drawerMode.value === "availability-create") {
      if (!resourceForm.modelIds.length) throw new Error("请选择至少一个模型");
      validateScope();
      await createLLMEntitlements({
        tenantId: tenantId.value,
        scopeType: scopeForm.scopeType,
        organizationUnitId: scopeForm.organizationUnitId,
        llmConfigIds: resourceForm.modelIds,
        status: resourceForm.status,
      });
      await loadTenantResources();
    } else if (drawerMode.value === "binding-create") {
      validateScope();
      if (!resourceForm.modelId) throw new Error("请选择默认模型");
      await createLLMBinding({
        tenantId: tenantId.value,
        scopeType: scopeForm.scopeType,
        organizationUnitId: scopeForm.organizationUnitId,
        llmConfigId: resourceForm.modelId,
        status: resourceForm.status,
        runtimeOverrides: {},
      });
      await loadTenantResources();
    } else if (selectedBinding.value) {
      await updateLLMBinding(selectedBinding.value.id, {
        llmConfigId: resourceForm.modelId,
        status: resourceForm.status,
        runtimeOverrides: selectedBinding.value.runtime_overrides,
      });
      await loadTenantResources();
    }
    drawerMode.value = null;
    ElMessage.success("保存成功");
  } catch (error) {
    notifyError(error, "保存失败");
  } finally {
    saving.value = false;
  }
}

function modelPayload() {
  if (!modelForm.alias.trim() || !modelForm.modelName.trim()) throw new Error("请填写别名与模型名称");
  return {
    alias: modelForm.alias.trim(), displayName: modelForm.displayName.trim(),
    provider: modelForm.provider, protocol: modelForm.protocol, modelName: modelForm.modelName.trim(),
    endpointUrl: modelForm.endpointUrl.trim(), status: modelForm.status,
    supportStream: modelForm.supportStream, supportTools: modelForm.supportTools,
    supportVision: modelForm.supportVision, supportThinking: modelForm.supportThinking,
    timeoutSeconds: Number(modelForm.timeoutSeconds) || 600,
    generationConfig: parseObject(modelForm.generationConfigText, "生成配置"),
    providerConfig: parseObject(modelForm.providerConfigText, "供应商配置"),
    credentials: parseObject(modelForm.credentialsText, "凭据"),
  };
}

function parseObject(text: string, label: string): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(text || "{}");
    if (!value || Array.isArray(value) || typeof value !== "object") throw new Error();
    return value as Record<string, unknown>;
  } catch {
    throw new Error(`${label}必须是合法的 JSON 对象`);
  }
}

function validateScope(): void {
  if (!tenantId.value) throw new Error("请选择租户");
  if (scopeForm.scopeType === "organization_unit" && !scopeForm.organizationUnitId) {
    throw new Error("请选择组织单元");
  }
}

function resetScopeForm(): void {
  scopeForm.scopeType = "tenant";
  scopeForm.organizationUnitId = "";
}

async function removeModel(model: ManagedLLMConfig): Promise<void> {
  await confirmDelete(model.display_name || model.alias);
  try {
    await deleteLLMModel(model.id);
    models.value = await listLLMModels({ pageSize: 100 });
  } catch (error) { notifyError(error, "删除模型失败"); }
}

async function toggleEntitlement(item: ManagedLLMEntitlement): Promise<void> {
  try {
    await updateLLMEntitlement(item.id, { status: item.status === "active" ? "inactive" : "active" });
    await loadTenantResources();
  } catch (error) { notifyError(error, "更新可用状态失败"); }
}

async function removeEntitlement(item: ManagedLLMEntitlement): Promise<void> {
  await confirmDelete(modelName(item.llm_config_id));
  try { await deleteLLMEntitlement(item.id); await loadTenantResources(); }
  catch (error) { notifyError(error, "删除可用模型失败"); }
}

async function removeBinding(item: ManagedLLMBinding): Promise<void> {
  await confirmDelete(scopeLabel(item.scope_type, item.organization_unit_id));
  try { await deleteLLMBinding(item.id); await loadTenantResources(); }
  catch (error) { notifyError(error, "删除绑定失败"); }
}

async function confirmDelete(label: string): Promise<void> {
  await ElMessageBox.confirm(`确定删除“${label}”吗？`, "删除确认", {
    type: "warning", confirmButtonText: "删除", cancelButtonText: "取消",
  });
}

function modelName(id: string): string {
  const model = modelMap.value.get(id);
  return model?.display_name || model?.alias || id;
}

function scopeLabel(type: LLMBindingScopeType, unitId: string): string {
  if (type === "tenant") return currentTenant.value?.tenant_name || "租户级";
  const path: string[] = [];
  let current = unitMap.value.get(unitId);
  const seen = new Set<string>();
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    path.unshift(current.name || current.external_key);
    current = current.parent_id ? unitMap.value.get(current.parent_id) : undefined;
  }
  return path.join(" / ") || unitId;
}

function notifyError(error: unknown, fallback: string): void {
  ElMessage.error(error instanceof ApiError || error instanceof Error ? error.message : fallback);
}

watch(tenantId, loadTenantResources);
watch(() => scopeForm.scopeType, (value) => { if (value === "tenant") scopeForm.organizationUnitId = ""; });
onMounted(loadAll);
</script>

<template>
  <div class="resource-page" v-loading="loading">
    <AppPanel class="resource-hero">
      <div class="resource-title">
        <span class="resource-icon"><el-icon><Cpu /></el-icon></span>
        <div><span class="eyebrow">MODEL GOVERNANCE</span><h1>模型管理</h1><p>统一配置模型，并将可用范围和默认绑定分配到任意组织层级。</p></div>
      </div>
      <div class="hero-actions">
        <el-select v-if="activeTab !== 'models'" v-model="tenantId" class="tenant-select" placeholder="选择租户">
          <el-option v-for="tenant in tenants" :key="tenant.id" :label="tenant.tenant_name || tenant.tenant_code" :value="tenant.id" />
        </el-select>
        <el-button :icon="Refresh" circle @click="loadAll" />
      </div>
    </AppPanel>

    <div class="resource-tabs">
      <button v-if="mode === 'global'" :class="{ active: activeTab === 'models' }" @click="activeTab = 'models'"><el-icon><Cpu /></el-icon>模型配置</button>
      <button :class="{ active: activeTab === 'availability' }" @click="activeTab = 'availability'"><el-icon><Tickets /></el-icon>可用模型</button>
      <button :class="{ active: activeTab === 'bindings' }" @click="activeTab = 'bindings'"><el-icon><Link /></el-icon>默认绑定</button>
    </div>

    <AppPanel class="table-card">
      <div class="table-head">
        <div><strong>{{ activeTab === 'models' ? '全局模型配置' : activeTab === 'availability' ? '组织可用模型' : '组织默认模型' }}</strong><small v-if="activeTab !== 'models'">{{ currentTenant?.tenant_name || '未选择租户' }}</small></div>
        <el-button v-if="activeTab === 'models'" type="primary" :icon="CirclePlus" @click="openCreateModel">新建模型</el-button>
        <el-button v-else-if="activeTab === 'availability'" type="primary" :icon="CirclePlus" :disabled="!tenantId" @click="openAvailability">分配模型</el-button>
        <el-button v-else type="primary" :icon="CirclePlus" :disabled="!tenantId" @click="openBinding()">新增绑定</el-button>
      </div>

      <el-table v-if="activeTab === 'models'" :data="models" class="resource-table">
        <el-table-column label="模型"><template #default="{ row }"><div class="primary-cell"><span>{{ row.display_name || row.alias }}</span><small>{{ row.model_name }}</small></div></template></el-table-column>
        <el-table-column prop="provider" label="供应商" width="140" />
        <el-table-column prop="protocol" label="协议" width="190" />
        <el-table-column label="能力" min-width="180"><template #default="{ row }"><el-space wrap><el-tag v-if="row.support_tools" size="small">Tools</el-tag><el-tag v-if="row.support_vision" size="small" type="success">Vision</el-tag><el-tag v-if="row.support_thinking" size="small" type="warning">Thinking</el-tag></el-space></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'primary' : 'info'">{{ row.status === 'active' ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><el-button link type="primary" :icon="EditPen" @click="openEditModel(row)">编辑</el-button><el-button link type="danger" :icon="Delete" @click="removeModel(row)">删除</el-button></template></el-table-column>
      </el-table>

      <el-table v-else-if="activeTab === 'availability'" :data="entitlements" class="resource-table">
        <el-table-column label="作用域" min-width="240"><template #default="{ row }"><div class="primary-cell"><span>{{ scopeLabel(row.scope_type, row.organization_unit_id) }}</span><small>{{ row.scope_type === 'tenant' ? '租户' : '组织单元' }}</small></div></template></el-table-column>
        <el-table-column label="可用模型" min-width="220"><template #default="{ row }">{{ modelName(row.llm_config_id) }}</template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="{ row }"><el-switch :model-value="row.status === 'active'" @change="toggleEntitlement(row)" /></template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="danger" :icon="Delete" @click="removeEntitlement(row)">删除</el-button></template></el-table-column>
      </el-table>

      <el-table v-else :data="bindings" class="resource-table">
        <el-table-column label="作用域" min-width="240"><template #default="{ row }"><div class="primary-cell"><span>{{ scopeLabel(row.scope_type, row.organization_unit_id) }}</span><small>向上回溯时优先采用最深层绑定</small></div></template></el-table-column>
        <el-table-column label="默认模型" min-width="220"><template #default="{ row }">{{ modelName(row.llm_config_id) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'primary' : 'info'">{{ row.status === 'active' ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="150"><template #default="{ row }"><el-button link type="primary" :icon="EditPen" @click="openBinding(row)">编辑</el-button><el-button link type="danger" :icon="Delete" @click="removeBinding(row)">删除</el-button></template></el-table-column>
      </el-table>
    </AppPanel>

    <el-drawer v-model="drawerMode" :title="drawerTitle" size="500px" destroy-on-close>
      <el-form v-if="drawerMode?.startsWith('model')" label-position="top">
        <div class="form-grid"><el-form-item label="别名" required><el-input v-model="modelForm.alias" :disabled="drawerMode === 'model-edit'" /></el-form-item><el-form-item label="显示名称"><el-input v-model="modelForm.displayName" /></el-form-item></div>
        <div class="form-grid"><el-form-item label="供应商"><el-select v-model="modelForm.provider"><el-option value="openai" label="OpenAI" /><el-option value="anthropic" label="Anthropic" /><el-option value="unicom" label="China Unicom" /></el-select></el-form-item><el-form-item label="协议"><el-select v-model="modelForm.protocol"><el-option value="openai-chat" label="OpenAI Chat" /><el-option value="anthropic-messages" label="Anthropic Messages" /><el-option value="chinaunicom-open-service" label="Unicom Open Service" /></el-select></el-form-item></div>
        <el-form-item label="模型名称" required><el-input v-model="modelForm.modelName" /></el-form-item>
        <el-form-item label="Endpoint"><el-input v-model="modelForm.endpointUrl" /></el-form-item>
        <el-form-item label="能力"><el-checkbox v-model="modelForm.supportStream">流式</el-checkbox><el-checkbox v-model="modelForm.supportTools">工具调用</el-checkbox><el-checkbox v-model="modelForm.supportVision">视觉</el-checkbox><el-checkbox v-model="modelForm.supportThinking">思考</el-checkbox></el-form-item>
        <el-form-item label="生成配置 JSON"><el-input v-model="modelForm.generationConfigText" type="textarea" :rows="4" /></el-form-item>
        <el-form-item label="供应商配置 JSON"><el-input v-model="modelForm.providerConfigText" type="textarea" :rows="4" /></el-form-item>
        <el-form-item v-if="drawerMode === 'model-create'" label="凭据 JSON"><el-input v-model="modelForm.credentialsText" type="textarea" :rows="4" /></el-form-item>
      </el-form>
      <el-form v-else label-position="top">
        <el-form-item label="作用域"><el-radio-group v-model="scopeForm.scopeType" :disabled="drawerMode === 'binding-edit'"><el-radio-button value="tenant">租户</el-radio-button><el-radio-button value="organization_unit">组织单元</el-radio-button></el-radio-group></el-form-item>
        <el-form-item v-if="scopeForm.scopeType === 'organization_unit'" label="组织单元" required><el-select v-model="scopeForm.organizationUnitId" filterable :disabled="drawerMode === 'binding-edit'"><el-option v-for="unit in units" :key="unit.id" :label="scopeLabel('organization_unit', unit.id)" :value="unit.id" /></el-select></el-form-item>
        <el-form-item v-if="drawerMode === 'availability-create'" label="可用模型" required><el-select v-model="resourceForm.modelIds" multiple filterable><el-option v-for="model in models" :key="model.id" :label="model.display_name || model.alias" :value="model.id" /></el-select></el-form-item>
        <el-form-item v-else label="默认模型" required><el-select v-model="resourceForm.modelId" filterable><el-option v-for="model in models" :key="model.id" :label="model.display_name || model.alias" :value="model.id" :disabled="!availableModelIds.has(model.id) && drawerMode === 'binding-create'" /></el-select><small class="form-hint">绑定模型必须位于该作用域的可用资源集合中。</small></el-form-item>
        <el-form-item label="状态"><el-radio-group v-model="resourceForm.status"><el-radio-button value="active">启用</el-radio-button><el-radio-button value="inactive">停用</el-radio-button></el-radio-group></el-form-item>
      </el-form>
      <template #footer><el-button @click="drawerMode = null">取消</el-button><el-button type="primary" :loading="saving" @click="saveDrawer">保存</el-button></template>
    </el-drawer>
  </div>
</template>

<style scoped>
.resource-page { display: grid; gap: 18px; }
.resource-hero { display: flex; align-items: center; justify-content: space-between; padding: 22px 26px; background: linear-gradient(118deg, #fff 58%, #eeebff); }
.resource-title, .hero-actions, .table-head, .resource-tabs { display: flex; align-items: center; gap: 14px; }
.resource-icon { display: grid; width: 48px; height: 48px; place-items: center; border-radius: 14px; background: linear-gradient(135deg, #4f46e5, #8b5cf6); color: #fff; font-size: 22px; }
.eyebrow { color: #6366f1; font-size: 10px; font-weight: 800; letter-spacing: .15em; }
h1 { margin: 3px 0; color: #24213e; font-size: 22px; } .resource-title p { margin: 0; color: #818197; }
.tenant-select { width: 220px; }
.resource-tabs { gap: 4px; padding: 4px; width: max-content; border: 1px solid #e1def0; border-radius: 13px; background: #fff; }
.resource-tabs button { display: flex; align-items: center; gap: 7px; padding: 9px 15px; border: 0; border-radius: 9px; background: transparent; color: #77758d; cursor: pointer; }
.resource-tabs button.active { background: #eeecff; color: #4f46e5; font-weight: 700; }
.table-card { padding: 0; overflow: hidden; }
.table-head { justify-content: space-between; padding: 18px 20px; border-bottom: 1px solid #ebe9f3; }
.table-head strong, .table-head small { display: block; } .table-head small { margin-top: 4px; color: #8c8ba0; }
.primary-cell span, .primary-cell small { display: block; } .primary-cell span { color: #2e2c48; font-weight: 700; } .primary-cell small, .form-hint { margin-top: 3px; color: #8b899e; font-size: 11px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 760px) { .resource-hero, .table-head { align-items: flex-start; flex-direction: column; } .hero-actions, .tenant-select { width: 100%; } .form-grid { grid-template-columns: 1fr; } }
</style>
