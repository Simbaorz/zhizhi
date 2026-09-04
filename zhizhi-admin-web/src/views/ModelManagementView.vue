<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { CirclePlus, Delete, EditPen, Refresh } from "@element-plus/icons-vue";

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
import FormDrawer from "@/components/FormDrawer.vue";
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
  "availability-create": "分配可用模型",
  "binding-create": "绑定默认模型",
  "binding-edit": "修改默认模型",
})[drawerMode.value ?? "model-create"]);
const drawerSubtitle = computed(() => {
  if (drawerMode.value === "model-create") return "添加一个可供平台分配的模型配置";
  if (drawerMode.value === "model-edit") {
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
  if (!saving.value) drawerMode.value = null;
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
      <el-button :icon="Refresh" @click="loadAll">刷新</el-button>
    </header>

    <section class="model-management-surface">
      <header class="model-management-toolbar">
        <nav class="model-management-tabs" aria-label="模型管理范围">
          <button
            v-if="mode === 'global'"
            type="button"
            :class="{ active: activeTab === 'models' }"
            @click="activeTab = 'models'"
          >
            模型配置
          </button>
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

        <div class="model-management-tools">
          <label v-if="activeTab !== 'models' && mode === 'global'" class="model-tenant-picker">
            <span>当前租户</span>
            <el-select v-model="tenantId" filterable placeholder="选择租户">
              <el-option
                v-for="tenant in tenants"
                :key="tenant.id"
                :label="tenant.tenant_name || tenant.tenant_code"
                :value="tenant.id"
              />
            </el-select>
          </label>
          <span v-else-if="activeTab !== 'models'" class="model-tenant-context">
            当前租户
            <strong>{{ currentTenant?.tenant_name || "未选择租户" }}</strong>
          </span>
          <el-button
            v-if="mode === 'global'"
            :icon="Refresh"
            circle
            aria-label="刷新模型管理数据"
            @click="loadAll"
          />
          <el-button
            v-if="activeTab === 'models'"
            type="primary"
            :icon="CirclePlus"
            @click="openCreateModel"
          >
            新建模型
          </el-button>
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

      <div class="model-table-region">
        <el-table
          v-if="activeTab === 'models'"
          :data="models"
          class="model-data-table"
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
              <span class="model-status" :class="row.status">
                <i />{{ row.status === "active" ? "启用" : "停用" }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170" fixed="right" align="right">
            <template #default="{ row }">
              <div class="model-row-actions">
                <el-button link type="primary" :icon="EditPen" @click="openEditModel(row)">编辑</el-button>
                <el-button link type="danger" :icon="Delete" @click="removeModel(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="还没有模型配置" :image-size="88" />
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

        <footer v-if="activeRecordCount" class="model-table-footer">
          共 {{ activeRecordCount }} {{ activeRecordUnit }}
        </footer>
      </div>
    </section>

    <FormDrawer
      :open="drawerMode !== null"
      :title="drawerTitle"
      :subtitle="drawerSubtitle"
      :saving="saving"
      size="wide"
      @close="closeDrawer"
      @submit="saveDrawer"
    >
      <el-form
        v-if="drawerMode?.startsWith('model')"
        class="model-drawer-form"
        label-position="top"
      >
        <div class="model-form-grid">
          <el-form-item label="别名" required>
            <el-input v-model="modelForm.alias" :disabled="drawerMode === 'model-edit'" />
          </el-form-item>
          <el-form-item label="显示名称">
            <el-input v-model="modelForm.displayName" />
          </el-form-item>
          <el-form-item label="供应商">
            <el-select v-model="modelForm.provider" :disabled="drawerMode === 'model-edit'">
              <el-option value="openai" label="OpenAI" />
              <el-option value="anthropic" label="Anthropic" />
            </el-select>
          </el-form-item>
          <el-form-item label="协议">
            <el-select v-model="modelForm.protocol" disabled>
              <el-option value="openai-chat" label="OpenAI Chat" />
              <el-option value="anthropic-messages" label="Anthropic Messages" />
            </el-select>
          </el-form-item>
          <el-form-item label="模型名称" required>
            <el-input v-model="modelForm.modelName" />
          </el-form-item>
          <el-form-item label="超时时间（秒）">
            <el-input-number v-model="modelForm.timeoutSeconds" :min="1" controls-position="right" />
          </el-form-item>
        </div>
        <el-form-item label="Endpoint">
          <el-input v-model="modelForm.endpointUrl" placeholder="留空时使用供应商默认地址" />
        </el-form-item>
        <el-form-item label="能力">
          <el-checkbox v-model="modelForm.supportStream">流式</el-checkbox>
          <el-checkbox v-model="modelForm.supportTools">工具调用</el-checkbox>
          <el-checkbox v-model="modelForm.supportVision">视觉</el-checkbox>
          <el-checkbox v-model="modelForm.supportThinking">思考</el-checkbox>
        </el-form-item>
        <div class="model-form-grid">
          <el-form-item label="生成配置 JSON">
            <el-input v-model="modelForm.generationConfigText" type="textarea" :rows="5" />
          </el-form-item>
          <el-form-item label="供应商配置 JSON">
            <el-input v-model="modelForm.providerConfigText" type="textarea" :rows="5" />
          </el-form-item>
        </div>
        <el-form-item v-if="drawerMode === 'model-create'" label="凭据 JSON">
          <el-input v-model="modelForm.credentialsText" type="textarea" :rows="5" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="modelForm.status">
            <el-radio-button value="active">启用</el-radio-button>
            <el-radio-button value="inactive">停用</el-radio-button>
          </el-radio-group>
        </el-form-item>
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
.model-drawer-form :deep(.el-input-number) {
  width: 100%;
}

.model-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 1rem;
}

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
}
</style>
