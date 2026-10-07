<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { CirclePlus, Delete, EditPen, Key, MagicStick, Refresh as RotateCcw, Search } from "@element-plus/icons-vue";

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
  listLLMModelPage,
  listOrganizationUnits,
  listOrgTenants,
  testLLMModel,
  updateLLMBinding,
  updateLLMEntitlement,
  updateLLMCredentials,
  updateLLMModel,
} from "@/api/admin";
import { ApiError } from "@/api/http";
import FormDrawer from "@/components/FormDrawer.vue";
import ManagementEmptyState from "@/components/ManagementEmptyState.vue";
import { RESOURCE_PAGE_SIZE } from "@/utils/pagination";
import { buildModelConfigs, modelConfigFields } from "@/utils/modelConfigForm";
import { formatDate } from "@/utils/format";
import { useScopeStore } from "@/stores/scope";
import type {
  LLMBindingScopeType,
  LLMProtocol,
  LLMProvider,
  LLMTestResult,
  ManagedLLMBinding,
  ManagedLLMConfig,
  ManagedLLMEntitlement,
  ManagedOrganizationUnit,
  ManagedTenant,
} from "@/types/admin";

const props = withDefaults(defineProps<{ mode?: "global" | "tenant" }>(), { mode: "tenant" });
type ActiveTab = "models" | "availability" | "bindings";
type DrawerMode = "model-create" | "model-edit" | "model-test" | "model-credentials" | "availability-create" | "binding-create" | "binding-edit";

const scopeStore = useScopeStore();
const activeTab = ref<ActiveTab>(props.mode === "global" ? "models" : "availability");
const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const testResult = ref<LLMTestResult | null>(null);
const testError = ref("");
const testForm = reactive({
  systemPrompt: "你是一个模型连通性测试助手。",
  prompt: "你好，请用一句话介绍自己。",
});
const tenants = ref<ManagedTenant[]>([]);
const units = ref<ManagedOrganizationUnit[]>([]);
const models = ref<ManagedLLMConfig[]>([]);
const entitlements = ref<ManagedLLMEntitlement[]>([]);
const bindings = ref<ManagedLLMBinding[]>([]);
const tenantId = ref("");
const drawerMode = ref<DrawerMode | null>(null);
const selectedModel = ref<ManagedLLMConfig | null>(null);
const CREDENTIAL_MASK = "********";
const credentialApiKey = ref("");
const credentialChanged = ref(false);
const credentialError = ref("");
const credentialConfigured = computed(() => selectedModel.value?.credential_fields?.includes("api_key") ?? selectedModel.value?.has_credentials ?? false);
const credentialsDirty = computed(() => credentialChanged.value && !!credentialApiKey.value.trim() && credentialApiKey.value.trim() !== CREDENTIAL_MASK);
const selectedBinding = ref<ManagedLLMBinding | null>(null);
const MODEL_PAGE_SIZE = RESOURCE_PAGE_SIZE;
const modelPage = ref(1);
const modelTotal = ref(0);
const modelSearch = ref("");

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
  ...modelConfigFields(),
  apiKey: "",
});
const protocolByProvider: Record<LLMProvider, LLMProtocol> = {
  openai: "openai-chat",
  anthropic: "anthropic-messages",
};
const resourceForm = reactive({ modelIds: [] as string[], modelId: "", status: "active" });

watch(() => modelForm.provider, (provider) => {
  modelForm.protocol = protocolByProvider[provider];
});

const drawerTitle = computed(() => ({
  "model-create": "新建模型配置",
  "model-edit": "编辑模型配置",
  "model-test": "模型连通测试",
  "model-credentials": "修改模型凭据",
  "availability-create": "分配可用模型",
  "binding-create": "绑定默认模型",
  "binding-edit": "修改默认模型",
})[drawerMode.value ?? "model-create"]);
const drawerSubtitle = computed(() => {
  if (drawerMode.value === "model-create") return "添加一个可供平台分配的模型配置";
  if (drawerMode.value?.startsWith("model")) {
    return selectedModel.value?.display_name || selectedModel.value?.alias || "";
  }
  if (drawerMode.value === "availability-create") {
    return `为“${currentTenant.value?.tenant_name || "当前租户"}”配置可用模型`;
  }
  return `设置“${currentTenant.value?.tenant_name || "当前租户"}”的默认模型`;
});
const currentTenant = computed(() => tenants.value.find((item) => item.id === tenantId.value));
const unitMap = computed(() => new Map(units.value.map((unit) => [unit.id, unit])));
const modelMap = computed(() => new Map(models.value.map((model) => [model.id, model])));
const availableModelIds = computed(() => new Set(entitlements.value.filter((item) => item.status === "active").map((item) => item.llm_config_id)));
const activeRecordCount = computed(() => {
  if (activeTab.value === "models") return models.value.length;
  return activeTab.value === "availability" ? entitlements.value.length : bindings.value.length;
});
const activeRecordUnit = computed(() => {
  if (activeTab.value === "models") return "个模型";
  return activeTab.value === "availability" ? "条可用配置" : "条默认配置";
});

async function loadAll(): Promise<void> {
  loading.value = true;
  try {
    if (props.mode === "global") {
      await loadModels();
      return;
    }
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

async function loadModels(): Promise<void> {
  if (props.mode !== "global") {
    models.value = await listLLMModels({ pageSize: 100 });
    return;
  }
  const result = await listLLMModelPage({
    page: modelPage.value, pageSize: MODEL_PAGE_SIZE, search: modelSearch.value.trim(),
  });
  const lastPage = Math.max(1, Math.ceil(result.pagination.total / MODEL_PAGE_SIZE));
  if (modelPage.value > lastPage) {
    modelPage.value = lastPage;
    await loadModels();
    return;
  }
  models.value = result.items;
  modelTotal.value = result.pagination.total;
}

function submitModelSearch(): void { modelPage.value = 1; void loadAll(); }
function resetModelSearch(): void { modelSearch.value = ""; submitModelSearch(); }
function changeModelPage(page: number): void { modelPage.value = page; void loadAll(); }

async function loadTenantResources(): Promise<void> {
  if (props.mode === "global") return;
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
    timeoutSeconds: 600, ...modelConfigFields(), apiKey: "",
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
    ...modelConfigFields(model.generation_config, model.provider_config),
    apiKey: "",
  });
  drawerMode.value = "model-edit";
}

function openTestModel(model: ManagedLLMConfig): void {
  selectedModel.value = model;
  testResult.value = null;
  testError.value = "";
  testForm.systemPrompt = "你是一个模型连通性测试助手。";
  testForm.prompt = "你好，请用一句话介绍自己。";
  drawerMode.value = "model-test";
}

function openModelCredentials(model: ManagedLLMConfig): void {
  selectedModel.value = model;
  credentialApiKey.value = credentialConfigured.value ? CREDENTIAL_MASK : "";
  credentialChanged.value = false;
  credentialError.value = "";
  drawerMode.value = "model-credentials";
}

function editCredential(): void {
  if (credentialChanged.value || saving.value) return;
  credentialApiKey.value = "";
  credentialChanged.value = true;
}

async function submitModelCredentials(): Promise<void> {
  if (!selectedModel.value || !credentialsDirty.value || saving.value) return;
  saving.value = true;
  credentialError.value = "";
  try {
    selectedModel.value = await updateLLMCredentials(selectedModel.value.id, {
      api_key: credentialApiKey.value.trim(),
    });
  } catch (error) {
    credentialError.value = error instanceof ApiError ? error.message : "更新模型凭据失败，请稍后重试。";
    return;
  } finally {
    saving.value = false;
  }
  closeDrawer();
  ElMessage.success("模型凭据已更新");
  try { await loadModels(); }
  catch (error) { notifyError(error, "刷新模型列表失败"); }
}

async function submitModelTest(): Promise<void> {
  if (!selectedModel.value || testing.value) return;
  testResult.value = null;
  testError.value = "";
  if (!testForm.prompt.trim()) {
    testError.value = "测试输入不能为空。";
    return;
  }
  testing.value = true;
  try {
    testResult.value = await testLLMModel(selectedModel.value.id, {
      prompt: testForm.prompt.trim(),
      systemPrompt: testForm.systemPrompt,
    });
  } catch (error) {
    testError.value = error instanceof ApiError ? error.message : "模型测试请求失败，请稍后重试。";
  } finally {
    testing.value = false;
  }
  if (testResult.value) {
    try { await loadModels(); }
    catch (error) { notifyError(error, "刷新模型测试状态失败"); }
  }
}

function testStatusLabel(status: string): string {
  if (status === "success") return "测试成功";
  if (status === "failed") return "测试失败";
  return "未测试";
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
  if (drawerMode.value === "model-test") {
    await submitModelTest();
    return;
  }
  if (drawerMode.value === "model-credentials") {
    await submitModelCredentials();
    return;
  }
  saving.value = true;
  try {
    if (drawerMode.value === "model-create") {
      await createLLMModel(modelPayload());
      await loadModels();
    } else if (drawerMode.value === "model-edit" && selectedModel.value) {
      const payload = modelPayload();
      await updateLLMModel(selectedModel.value.id, payload);
      await loadModels();
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
    modelForm.apiKey = "";
    credentialApiKey.value = "";
    credentialChanged.value = false;
    credentialError.value = "";
    ElMessage.success("保存成功");
  } catch (error) {
    notifyError(error, "保存失败");
  } finally {
    saving.value = false;
  }
}

function modelPayload() {
  if (!modelForm.alias.trim() || !modelForm.modelName.trim()) throw new Error("请填写别名与模型名称");
  if (!Number.isSafeInteger(modelForm.timeoutSeconds) || modelForm.timeoutSeconds < 1) {
    throw new Error("超时秒数必须是大于零的整数");
  }
  return {
    alias: modelForm.alias.trim(), displayName: modelForm.displayName.trim(),
    provider: modelForm.provider, protocol: modelForm.protocol, modelName: modelForm.modelName.trim(),
    endpointUrl: modelForm.endpointUrl.trim(), status: modelForm.status,
    supportStream: modelForm.supportStream, supportTools: modelForm.supportTools,
    supportVision: modelForm.supportVision, supportThinking: modelForm.supportThinking,
    timeoutSeconds: modelForm.timeoutSeconds,
    ...buildModelConfigs(modelForm, selectedModel.value?.generation_config, selectedModel.value?.provider_config),
    credentials: modelForm.apiKey.trim() ? { api_key: modelForm.apiKey.trim() } : {},
  };
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
    await loadModels();
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

function providerLabel(provider: LLMProvider): string {
  return provider === "anthropic" ? "Anthropic" : "OpenAI";
}

function protocolLabel(protocol: LLMProtocol): string {
  return protocol === "anthropic-messages" ? "Anthropic Messages" : "OpenAI Chat";
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

function closeDrawer(): void {
  if (!saving.value && !testing.value) {
    drawerMode.value = null;
    modelForm.apiKey = "";
    credentialApiKey.value = "";
    credentialChanged.value = false;
    credentialError.value = "";
  }
}

watch(tenantId, loadTenantResources);
watch(() => scopeForm.scopeType, (value) => { if (value === "tenant") scopeForm.organizationUnitId = ""; });
onMounted(loadAll);
</script>

<template>
  <div
    class="model-management-page"
    :class="{ 'is-global-mode': mode === 'global' }"
    v-loading="loading"
  >
    <header v-if="mode === 'tenant'" class="model-local-head">
      <div>
        <h1>模型管理</h1>
        <p>管理当前租户的可用模型与默认模型。</p>
      </div>
    </header>

    <section class="model-management-surface">
      <header class="model-management-toolbar global-resource-toolbar">
        <h2 v-if="mode === 'global'" class="model-global-title global-resource-title">模型配置</h2>
        <nav v-else class="model-management-tabs" aria-label="模型管理范围">
          <button
            type="button"
            :class="{ active: activeTab === 'availability' }"
            @click="activeTab = 'availability'"
          >
            可用模型
          </button>
          <button
            type="button"
            :class="{ active: activeTab === 'bindings' }"
            @click="activeTab = 'bindings'"
          >
            默认模型
          </button>
        </nav>

        <div class="model-management-tools global-resource-tools">
          <div v-if="mode === 'global'" class="model-search-tools global-resource-filters">
            <el-input v-model="modelSearch" :prefix-icon="Search" clearable placeholder="搜索别名、名称或模型" @keydown.enter="submitModelSearch" />
            <el-button :icon="RotateCcw" :disabled="loading" @click="resetModelSearch">重置</el-button>
            <el-button :icon="Search" type="primary" :disabled="loading" @click="submitModelSearch">搜索</el-button>
          </div>
          <span v-else class="model-tenant-context">
            当前租户
            <strong>{{ currentTenant?.tenant_name || "未选择租户" }}</strong>
          </span>
          <div v-if="activeTab === 'models'" class="global-resource-actions">
          <el-button
            type="primary"
            :icon="CirclePlus"
            @click="openCreateModel"
          >
            新建模型
          </el-button>
          </div>
          <el-button
            v-else-if="activeTab === 'availability'"
            type="primary"
            :icon="CirclePlus"
            :disabled="!tenantId"
            @click="openAvailability"
          >
            分配模型
          </el-button>
          <el-button
            v-else
            type="primary"
            :icon="CirclePlus"
            :disabled="!tenantId"
            @click="openBinding()"
          >
            设置默认模型
          </el-button>
        </div>
      </header>

      <div class="model-table-region global-resource-table-region">
        <el-table
          v-if="activeTab === 'models'"
          :data="models"
          class="model-data-table global-resource-table"
          row-key="id"
          height="100%"
        >
          <el-table-column label="模型" min-width="240">
            <template #default="{ row }">
              <div class="model-primary-cell">
                <strong>{{ row.display_name || row.alias }}</strong>
                <small>{{ row.model_name }}</small>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="供应商" width="140">
            <template #default="{ row }">{{ providerLabel(row.provider) }}</template>
          </el-table-column>
          <el-table-column label="协议" min-width="180">
            <template #default="{ row }">{{ protocolLabel(row.protocol) }}</template>
          </el-table-column>
          <el-table-column label="能力" min-width="250">
            <template #default="{ row }">
              <div class="model-capabilities">
                <span v-if="row.support_stream">流式</span>
                <span v-if="row.support_tools">工具调用</span>
                <span v-if="row.support_vision">视觉</span>
                <span v-if="row.support_thinking">思考</span>
                <small v-if="!row.support_stream && !row.support_tools && !row.support_vision && !row.support_thinking">—</small>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === "active" ? "启用" : "停用" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="测试" min-width="210">
            <template #default="{ row }">
              <div class="model-test-cell">
                <el-tag :type="row.last_test_status === 'success' ? 'success' : row.last_test_status === 'failed' ? 'danger' : 'info'" :title="row.last_test_time ? `最近测试：${formatDate(row.last_test_time)}` : '尚未执行测试'">
                  {{ testStatusLabel(row.last_test_status) }}
                </el-tag>
                <small :title="row.last_test_message">{{ row.last_test_message || "尚未执行测试" }}</small>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="300" fixed="right" align="right">
            <template #default="{ row }">
              <div class="model-row-actions global-resource-row-actions">
                <el-button link type="primary" :icon="MagicStick" :disabled="row.status !== 'active'" :title="row.status === 'active' ? '用当前配置发起一次模型调用' : '请先启用模型再测试'" @click="openTestModel(row)">测试</el-button>
                <el-button link type="primary" :icon="Key" title="修改模型 API Key" @click="openModelCredentials(row)">凭据</el-button>
                <el-button link type="primary" :icon="EditPen" @click="openEditModel(row)">编辑</el-button>
                <el-button link type="danger" :icon="Delete" @click="removeModel(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
          <template #empty>
            <ManagementEmptyState
              :title="modelSearch.trim() ? '未找到匹配的模型' : '暂无模型配置'"
              :description="modelSearch.trim() ? '请调整搜索条件后重试。' : '登记模型后，可在模型管理中分配可用模型和配置默认模型。'"
            >
              <el-button v-if="!modelSearch.trim()" type="primary" @click="openCreateModel">创建第一个模型</el-button>
            </ManagementEmptyState>
          </template>
        </el-table>

        <el-table
          v-else-if="activeTab === 'availability'"
          :data="entitlements"
          class="model-data-table"
          row-key="id"
          height="100%"
        >
          <el-table-column label="作用域" min-width="280">
            <template #default="{ row }">
              <div class="model-primary-cell">
                <strong>{{ scopeLabel(row.scope_type, row.organization_unit_id) }}</strong>
                <small>{{ row.scope_type === "tenant" ? "租户" : "组织单元" }}</small>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="可用模型" min-width="260">
            <template #default="{ row }">{{ modelName(row.llm_config_id) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-switch
                :model-value="row.status === 'active'"
                @change="toggleEntitlement(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="right">
            <template #default="{ row }">
              <el-button link type="danger" :icon="Delete" @click="removeEntitlement(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty
              :description="tenantId ? '尚未分配可用模型' : '请先选择租户'"
              :image-size="88"
            />
          </template>
        </el-table>

        <el-table
          v-else
          :data="bindings"
          class="model-data-table"
          row-key="id"
          height="100%"
        >
          <el-table-column label="作用域" min-width="300">
            <template #default="{ row }">
              <div class="model-primary-cell">
                <strong>{{ scopeLabel(row.scope_type, row.organization_unit_id) }}</strong>
                <small>未绑定时向上回溯到最近的组织层级</small>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="默认模型" min-width="260">
            <template #default="{ row }">{{ modelName(row.llm_config_id) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <span class="model-status" :class="row.status">
                <i />{{ row.status === "active" ? "启用" : "停用" }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170" align="right">
            <template #default="{ row }">
              <div class="model-row-actions">
                <el-button link type="primary" :icon="EditPen" @click="openBinding(row)">编辑</el-button>
                <el-button link type="danger" :icon="Delete" @click="removeBinding(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty
              :description="tenantId ? '尚未设置默认模型' : '请先选择租户'"
              :image-size="88"
            />
          </template>
        </el-table>

        <footer v-if="activeTab !== 'models' && activeRecordCount" class="model-table-footer">
          共 {{ activeRecordCount }} {{ activeRecordUnit }}
        </footer>
      </div>
      <el-pagination
        v-if="activeTab === 'models' && modelTotal > 0"
        class="admin-pagination"
        :current-page="modelPage"
        :page-size="MODEL_PAGE_SIZE"
        :total="modelTotal"
        layout="total, prev, pager, next"
        @current-change="changeModelPage"
      />
    </section>

    <FormDrawer
      :open="drawerMode !== null"
      :class="{ 'global-resource-form-dialog': props.mode === 'global' }"
      :title="drawerTitle"
      :subtitle="drawerSubtitle"
      :saving="saving || testing"
      :submit-text="drawerMode === 'model-test' ? '开始测试' : drawerMode === 'model-credentials' ? '保存凭据' : '保存'"
      :submit-disabled="drawerMode === 'model-credentials' && !credentialsDirty"
      :placement="drawerMode?.startsWith('model') ? 'modal' : 'drawer'"
      :size="drawerMode?.startsWith('model') ? 'default' : 'wide'"
      @close="closeDrawer"
      @submit="saveDrawer"
    >
      <el-form
        v-if="drawerMode === 'model-create' || drawerMode === 'model-edit'"
        class="model-config-form"
        tag="div"
        label-position="top"
      >
        <div class="model-form-grid">
          <el-form-item label="别名" required>
            <el-input v-model="modelForm.alias" placeholder="main-chat" :disabled="drawerMode === 'model-edit'" />
          </el-form-item>
          <el-form-item label="显示名称">
            <el-input v-model="modelForm.displayName" placeholder="主力对话模型" />
          </el-form-item>
          <el-form-item label="模型来源">
            <el-select v-model="modelForm.provider" :disabled="drawerMode === 'model-edit'">
              <el-option value="openai" label="OpenAI Compatible" />
              <el-option value="anthropic" label="Anthropic" />
            </el-select>
          </el-form-item>
          <el-form-item label="协议">
            <el-input v-model="modelForm.protocol" disabled />
          </el-form-item>
          <el-form-item label="模型名称" required>
            <el-input v-model="modelForm.modelName" placeholder="gpt-4.1 / claude-sonnet" />
          </el-form-item>
          <el-form-item label="接口地址">
            <el-input v-model="modelForm.endpointUrl" placeholder="https://api.example.com/v1" />
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="modelForm.status">
              <el-option value="active" label="启用" />
              <el-option value="inactive" label="停用" />
            </el-select>
          </el-form-item>
          <el-form-item label="超时秒数">
            <el-input-number v-model="modelForm.timeoutSeconds" :min="1" :precision="0" :controls="false" />
          </el-form-item>
          <el-form-item label="上下文窗口" required>
            <el-input v-model="modelForm.contextWindow" type="number" min="1" />
          </el-form-item>
        </div>
        <section class="model-capability-section" aria-label="模型能力">
          <h3>模型能力</h3>
          <div class="model-capability-grid">
            <el-checkbox v-model="modelForm.supportStream">流式输出</el-checkbox>
            <el-checkbox v-model="modelForm.supportTools">工具调用</el-checkbox>
            <el-checkbox v-model="modelForm.supportVision">视觉输入</el-checkbox>
            <el-checkbox v-model="modelForm.supportThinking">思考能力</el-checkbox>
          </div>
        </section>
        <div class="model-form-grid model-generation-grid">
          <el-form-item label="temperature">
            <el-input v-model="modelForm.temperature" placeholder="0 至 2，留空使用模型默认值" />
          </el-form-item>
          <el-form-item label="top_p">
            <el-input v-model="modelForm.topP" placeholder="0 至 1" />
          </el-form-item>
          <el-form-item label="max_tokens">
            <el-input v-model="modelForm.maxTokens" placeholder="正整数" />
          </el-form-item>
          <el-form-item label="presence_penalty">
            <el-input v-model="modelForm.presencePenalty" placeholder="-2 至 2" />
          </el-form-item>
          <el-form-item label="frequency_penalty">
            <el-input v-model="modelForm.frequencyPenalty" placeholder="-2 至 2" />
          </el-form-item>
          <el-form-item label="seed">
            <el-input v-model="modelForm.seed" placeholder="可选，非负整数" />
          </el-form-item>
        </div>
        <el-form-item v-if="modelForm.provider === 'anthropic'" label="Anthropic Version">
          <el-input model-value="2023-06-01" disabled />
        </el-form-item>
        <div v-if="drawerMode === 'model-create'" class="model-form-grid">
          <el-form-item label="API Key">
            <el-input v-model="modelForm.apiKey" type="password" autocomplete="new-password" />
          </el-form-item>
        </div>
      </el-form>

      <el-form v-else-if="drawerMode === 'model-credentials'" class="model-credentials-form" tag="div" label-position="top">
        <div class="model-credential-summary" :class="{ dirty: credentialChanged }">
          <strong>{{ credentialChanged ? '有未保存变更' : '凭据未变更' }}</strong>
          <small>{{ credentialConfigured ? '已配置字段显示为 ********，点击输入框后可重新填写并保存。' : '尚未配置 API Key，请填写后保存。' }}</small>
        </div>
        <el-form-item label="API Key" required>
          <el-input
            v-model="credentialApiKey"
            type="password" autocomplete="new-password"
            :disabled="saving"
            placeholder="输入新的 API Key"
            @focus="editCredential"
            @update:model-value="credentialChanged = true"
          />
          <small class="model-form-hint">{{ credentialChanged ? '请填写完整的新凭据后保存' : credentialConfigured ? '未变更' : '未配置' }}</small>
        </el-form-item>
        <el-alert v-if="credentialError" :title="credentialError" type="error" show-icon :closable="false" />
      </el-form>

      <el-form v-else-if="drawerMode === 'model-test'" class="model-test-form" tag="div" label-position="top">
        <el-form-item label="System Prompt">
          <el-input v-model="testForm.systemPrompt" type="textarea" :rows="3" :disabled="testing" />
        </el-form-item>
        <el-form-item label="测试输入" required>
          <el-input v-model="testForm.prompt" type="textarea" :rows="4" :disabled="testing" />
        </el-form-item>
        <div v-if="testing" class="model-test-progress" role="status">
          <el-icon class="is-loading"><RotateCcw /></el-icon>
          正在调用模型，请稍候…
        </div>
        <el-alert v-if="testError" :title="testError" type="error" show-icon :closable="false" />
        <section v-if="testResult" class="model-test-result" aria-label="模型测试结果" aria-live="polite">
          <el-alert
            :type="testResult.ok ? 'success' : 'error'"
            :title="`${testResult.ok ? '测试成功' : '测试失败'} · ${testResult.latency_ms} ms`"
            :description="testResult.ok ? (testResult.content || '模型调用成功，未返回文本内容。') : testResult.error"
            show-icon
            :closable="false"
          />
          <div v-if="testResult.usage" class="model-test-usage">
            <span>输入 Token：{{ testResult.usage.input_tokens }}</span>
            <span>输出 Token：{{ testResult.usage.output_tokens }}</span>
            <span>总计 Token：{{ testResult.usage.total_tokens }}</span>
          </div>
        </section>
      </el-form>

      <el-form v-else class="model-drawer-form" label-position="top">
        <el-form-item label="作用域">
          <el-radio-group
            v-model="scopeForm.scopeType"
            :disabled="drawerMode === 'binding-edit'"
          >
            <el-radio-button value="tenant">租户</el-radio-button>
            <el-radio-button value="organization_unit">组织单元</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          v-if="scopeForm.scopeType === 'organization_unit'"
          label="组织单元"
          required
        >
          <el-select
            v-model="scopeForm.organizationUnitId"
            filterable
            :disabled="drawerMode === 'binding-edit'"
          >
            <el-option
              v-for="unit in units"
              :key="unit.id"
              :label="scopeLabel('organization_unit', unit.id)"
              :value="unit.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="drawerMode === 'availability-create'" label="可用模型" required>
          <el-select v-model="resourceForm.modelIds" multiple filterable>
            <el-option
              v-for="model in models"
              :key="model.id"
              :label="model.display_name || model.alias"
              :value="model.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="默认模型" required>
          <el-select v-model="resourceForm.modelId" filterable>
            <el-option
              v-for="model in models"
              :key="model.id"
              :label="model.display_name || model.alias"
              :value="model.id"
              :disabled="!availableModelIds.has(model.id) && drawerMode === 'binding-create'"
            />
          </el-select>
          <small class="model-form-hint">默认模型必须已经分配到该作用域的可用模型集合中。</small>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="resourceForm.status">
            <el-radio-button value="active">启用</el-radio-button>
            <el-radio-button value="inactive">停用</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
    </FormDrawer>
  </div>
</template>

<style scoped>
.model-management-page {
  --model-control-height: 2rem;
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}

.model-local-head {
  display: flex;
  min-height: 72px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  border: 1px solid rgba(215, 222, 226, 0.9);
  border-bottom: 0;
  padding: 14px 24px;
}

.model-local-head h1,
.model-local-head p {
  margin: 0;
}

.model-local-head h1 {
  font-size: 18px;
}

.model-local-head p {
  margin-top: 3px;
  color: var(--text-secondary);
  font-size: 12px;
}

.model-management-surface {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(215, 222, 226, 0.9);
  background: #fff;
}

.model-management-page.is-global-mode .model-management-surface {
  border: 0;
}

.model-management-toolbar {
  display: flex;
  min-height: 3.75rem;
  flex: 0 0 auto;
  align-items: center;
  gap: 1rem;
  border-bottom: 1px solid rgba(219, 222, 234, 0.92);
  padding: 0.75rem 1.25rem;
}

.model-global-title { margin: 0; font-size: 0.9375rem; font-weight: 700; white-space: nowrap; }
.model-search-tools { display: flex; align-items: center; gap: 0.625rem; }
.model-search-tools .el-input { width: 240px; }

.model-management-tabs {
  display: flex;
  align-self: stretch;
  flex: 0 0 auto;
  align-items: stretch;
  gap: 1.5rem;
}

.model-management-tabs button {
  position: relative;
  border: 0;
  background: transparent;
  padding: 0 0.125rem;
  color: var(--text-secondary);
  font-size: 0.8125rem;
  font-weight: 720;
  cursor: pointer;
  transition: color 140ms ease;
}

.model-management-tabs button:hover,
.model-management-tabs button.active {
  color: var(--accent);
}

.model-management-tabs button.active::after {
  position: absolute;
  right: 0;
  bottom: -0.75rem;
  left: 0;
  height: 2px;
  border-radius: 999px;
  background: var(--accent);
  content: "";
}

.model-management-tools {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 0.625rem;
}

.model-management-tools > .el-button:last-child {
  min-width: 7.75rem;
  height: var(--model-control-height);
  min-height: var(--model-control-height);
  padding-inline: 0.875rem;
}

.model-tenant-picker,
.model-tenant-context {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  color: var(--text-tertiary);
  font-size: 0.75rem;
  white-space: nowrap;
}

.model-tenant-picker .el-select {
  width: 13.75rem;
}

.model-tenant-picker :deep(.el-select__wrapper) {
  min-height: var(--model-control-height);
  border-radius: var(--el-border-radius-base);
  box-shadow: 0 0 0 1px rgba(205, 209, 224, 0.95) inset;
}

.model-tenant-context strong {
  color: var(--text-primary);
  font-size: 0.8125rem;
}

.model-table-region {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
}

.model-data-table {
  flex: 1 1 auto;
  --el-table-border-color: rgba(220, 223, 234, 0.92);
  --el-table-header-bg-color: #fbfbfd;
  --el-table-row-hover-bg-color: #f8f7ff;
}

.model-data-table :deep(.el-table__inner-wrapper::before) {
  display: none;
}

.model-data-table :deep(th.el-table__cell) {
  height: 2.875rem;
  background: #fbfbfd;
  color: #59586d;
  font-size: 0.8125rem;
  font-weight: 760;
}

.model-data-table :deep(td.el-table__cell) {
  height: 3.25rem;
  color: #3f3e54;
  font-size: 0.8125rem;
}

.model-data-table :deep(.cell) {
  padding-right: 0.875rem;
  padding-left: 0.875rem;
}

.model-primary-cell strong,
.model-primary-cell small {
  display: block;
}

.model-primary-cell strong {
  color: #29283d;
  font-weight: 720;
}

.model-primary-cell small,
.model-form-hint {
  margin-top: 3px;
  color: var(--text-tertiary);
  font-size: 11px;
}

.model-capabilities,
.model-row-actions {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.model-capabilities {
  flex-wrap: wrap;
}

.model-capabilities span {
  border: 1px solid rgba(207, 210, 227, 0.92);
  border-radius: 999px;
  padding: 0.125rem 0.4375rem;
  background: #fafafe;
  color: #65637b;
  font-size: 0.6875rem;
  line-height: 1.35;
}

.model-row-actions {
  justify-content: flex-end;
}

.model-status {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: #4e4c62;
}

.model-status i {
  width: 0.4375rem;
  height: 0.4375rem;
  border-radius: 50%;
  background: #a8a7b4;
}

.model-status.active i {
  background: #18a566;
}

.model-table-footer {
  display: flex;
  min-height: 3.5rem;
  flex: 0 0 auto;
  align-items: center;
  border-top: 1px solid rgba(220, 223, 234, 0.92);
  padding: 0 1.25rem;
  color: var(--text-secondary);
  font-size: 0.75rem;
}

.model-drawer-form :deep(.el-select),
.model-drawer-form :deep(.el-input-number),
.model-config-form :deep(.el-select),
.model-config-form :deep(.el-input-number) {
  width: 100%;
}

.model-config-form :deep(.el-form-item) { margin-bottom: 12px; }
.model-config-form :deep(.el-form-item__label) {
  height: auto;
  margin-bottom: 4px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  line-height: 16px;
}
.model-config-form :deep(.el-input-number .el-input__inner) { text-align: left; }
.model-test-cell { display: grid; justify-items: start; gap: 4px; }
.model-test-cell small {
  max-width: 100%;
  overflow: hidden;
  color: var(--text-tertiary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-test-form { width: 100%; }
.model-credentials-form { width: 100%; }
.model-credential-summary {
  display: grid;
  gap: 6px;
  margin-bottom: 16px;
  border: 1px solid var(--border-weak);
  border-radius: 8px;
  padding: 12px;
  color: var(--text-secondary);
  font-size: 13px;
}
.model-credential-summary small { font-size: 12px; line-height: 1.5; }
.model-credential-summary.dirty { border-color: var(--accent); }
.model-credentials-form :deep(.el-form-item__label) { color: var(--text-secondary); font-size: 12px; }
.model-test-form :deep(.el-form-item__label) { color: var(--text-secondary); font-size: 12px; }
.model-test-progress, .model-test-usage {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 16px;
  color: var(--text-secondary);
  font-size: 13px;
}
.model-test-result :deep(.el-alert__description) { white-space: pre-wrap; overflow-wrap: anywhere; }
.model-test-usage { margin-top: 12px; border: 1px solid var(--border-weak); border-radius: 8px; padding: 12px; }
.model-capability-section {
  margin: 4px 0 16px;
  border: 1px solid var(--border-weak);
  border-radius: 8px;
  padding: 12px;
}
.model-capability-section h3 {
  margin: 0 0 12px;
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 600;
}
.model-capability-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.model-capability-grid :deep(.el-checkbox) { margin-right: 0; }
.model-capability-grid :deep(.el-checkbox__label) { font-size: 12px; }

.model-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 12px;
}

.model-generation-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }

.model-form-hint {
  display: block;
}

@media (max-width: 980px) {
  .model-management-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .model-management-tabs {
    min-height: 2.25rem;
  }

  .model-management-tabs button.active::after {
    bottom: -0.75rem;
  }

  .model-management-tools {
    width: 100%;
    justify-content: flex-start;
  }

  .model-management-tools > .el-button:last-child {
    margin-left: auto;
  }
}

@media (max-width: 680px) {
  .model-management-tools {
    align-items: stretch;
    flex-wrap: wrap;
  }

  .model-tenant-picker,
  .model-tenant-context,
  .model-tenant-picker .el-select {
    width: 100%;
  }

  .model-form-grid {
    grid-template-columns: 1fr;
  }

  .model-capability-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
