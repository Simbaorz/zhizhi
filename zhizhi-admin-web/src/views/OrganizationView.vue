<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";
import {
  ArrowRight,
  CirclePlus,
  Delete,
  EditPen,
  OfficeBuilding,
  Refresh as RotateCcw,
  Search,
} from "@element-plus/icons-vue";

import {
  createOrganizationUnit,
  createOrgTenant,
  deleteOrganizationUnit,
  deleteOrgTenant,
  listOrganizationUnits,
  listOrgTenantPage,
  updateOrganizationUnit,
  updateOrgTenant,
} from "@/api/admin";
import { ApiError } from "@/api/http";
import FormDrawer from "@/components/FormDrawer.vue";
import ManagementEmptyState from "@/components/ManagementEmptyState.vue";
import { RESOURCE_PAGE_SIZE } from "@/utils/pagination";
import { useAuthStore } from "@/stores/auth";
import { useScopeStore } from "@/stores/scope";
import type { ManagedOrganizationUnit, ManagedTenant } from "@/types/admin";

interface OrganizationTreeNode extends ManagedOrganizationUnit {
  children: OrganizationTreeNode[];
}

interface OrganizationTableRow extends ManagedOrganizationUnit {
  tree_depth: number;
  has_children: boolean;
}

type DrawerMode = "tenant-create" | "tenant-edit" | "unit-create" | "unit-edit";
type ManagementSection = "tenants" | "organization";

const TENANT_PAGE_SIZE = RESOURCE_PAGE_SIZE;
const TENANT_CATALOG_SIZE = 100;

const props = withDefaults(defineProps<{ mode?: "global" | "tenant" }>(), {
  mode: "tenant",
});

const authStore = useAuthStore();
const scopeStore = useScopeStore();
const router = useRouter();

const loading = ref(false);
const tableLoading = ref(false);
const saving = ref(false);
const activeSection = computed<ManagementSection>(() => props.mode === "global" ? "tenants" : "organization");
const tenantRows = ref<ManagedTenant[]>([]);
const tenantOptions = ref<ManagedTenant[]>([]);
const tenantTotal = ref(0);
const tenantPage = ref(1);
const tenantSearch = ref("");
const activeTenantId = ref("");
const units = ref<ManagedOrganizationUnit[]>([]);
const expandedUnitIds = ref<string[]>([]);
const editingTenantId = ref("");
const editingUnitId = ref("");
const drawerMode = ref<DrawerMode | null>(null);

const tenantForm = reactive({ tenantCode: "", tenantName: "", status: "active" });
const unitForm = reactive({
  parentId: "",
  externalKey: "",
  name: "",
  unitType: "",
  metadataText: "{}",
  status: "active",
  sortOrder: 0,
});

const canManageTenants = computed(
  () => props.mode === "global" && authStore.isSuper,
);
const canManageOrganization = computed(
  () => authStore.isSuper || authStore.permissionCodes.includes("org.manage"),
);
const activeTenant = computed(() => findTenant(activeTenantId.value));
const editingTenant = computed(() => findTenant(editingTenantId.value));
const editingUnit = computed(
  () => units.value.find((unit) => unit.id === editingUnitId.value) ?? null,
);
const drawerTitle = computed(
  () =>
    ({
      "tenant-create": "新建租户",
      "tenant-edit": "编辑租户",
      "unit-create": "新建组织单元",
      "unit-edit": "编辑组织单元",
    })[drawerMode.value ?? "tenant-create"],
);
const drawerSubtitle = computed(() => {
  if (drawerMode.value === "tenant-create") {
    return "创建企业数据、权限与资源分配的最高边界";
  }
  if (drawerMode.value === "tenant-edit") {
    return editingTenant.value?.tenant_code ?? "";
  }
  if (drawerMode.value === "unit-create") {
    return unitForm.parentId
      ? `在“${parentNameById(unitForm.parentId)}”下创建下级组织`
      : `在“${activeTenant.value?.tenant_name ?? "当前租户"}”下创建根组织`;
  }
  return editingUnit.value?.external_key ?? "";
});
const organizationTree = computed<OrganizationTreeNode[]>(() =>
  buildOrganizationTree(units.value),
);
const organizationRows = computed<OrganizationTableRow[]>(() =>
  flattenOrganizationTree(organizationTree.value),
);
const parentOptions = computed(() => {
  const blocked = new Set<string>();
  if (drawerMode.value === "unit-edit" && editingUnit.value) {
    collectDescendants(editingUnit.value.id, blocked);
    blocked.add(editingUnit.value.id);
  }
  return units.value.filter((unit) => !blocked.has(unit.id));
});

function buildOrganizationTree(source: ManagedOrganizationUnit[]): OrganizationTreeNode[] {
  const map = new Map(
    source.map((unit) => [unit.id, { ...unit, children: [] } as OrganizationTreeNode]),
  );
  const roots: OrganizationTreeNode[] = [];
  for (const unit of map.values()) {
    const parent = unit.parent_id ? map.get(unit.parent_id) : undefined;
    if (parent) parent.children.push(unit);
    else roots.push(unit);
  }
  const sort = (nodes: OrganizationTreeNode[]): void => {
    nodes.sort(
      (left, right) =>
        left.sort_order - right.sort_order
        || (left.name || left.external_key).localeCompare(
          right.name || right.external_key,
          "zh-CN",
        ),
    );
    nodes.forEach((node) => sort(node.children));
  };
  sort(roots);
  return roots;
}

function flattenOrganizationTree(
  source: OrganizationTreeNode[],
  depth = 0,
): OrganizationTableRow[] {
  const rows: OrganizationTableRow[] = [];
  for (const node of source) {
    const { children, ...unit } = node;
    rows.push({
      ...unit,
      tree_depth: depth,
      has_children: children.length > 0,
    });
    if (children.length && expandedUnitIds.value.includes(node.id)) {
      rows.push(...flattenOrganizationTree(children, depth + 1));
    }
  }
  return rows;
}

function findTenant(tenantId: string): ManagedTenant | null {
  return (
    tenantOptions.value.find((tenant) => tenant.id === tenantId)
    ?? tenantRows.value.find((tenant) => tenant.id === tenantId)
    ?? null
  );
}

async function loadTenantCatalog(): Promise<void> {
  const result = await listOrgTenantPage({
    page: 1,
    pageSize: TENANT_CATALOG_SIZE,
    search: "",
    status: "all",
  });
  tenantOptions.value = result.items;
  const preferredTenantId = activeTenantId.value || scopeStore.currentTenantId;
  if (preferredTenantId && findTenant(preferredTenantId)) {
    activeTenantId.value = preferredTenantId;
  } else if (!findTenant(activeTenantId.value)) {
    activeTenantId.value = tenantOptions.value[0]?.id ?? "";
  }
  syncTenantContext(activeTenantId.value);
}

async function loadTenantRows(): Promise<void> {
  tableLoading.value = true;
  try {
    const result = await listOrgTenantPage({
      page: tenantPage.value,
      pageSize: TENANT_PAGE_SIZE,
      search: tenantSearch.value.trim(),
      status: "all",
    });
    const lastPage = Math.max(1, Math.ceil(result.pagination.total / TENANT_PAGE_SIZE));
    if (tenantPage.value > lastPage) {
      tenantPage.value = lastPage;
      await loadTenantRows();
      return;
    }
    tenantRows.value = result.items;
    tenantTotal.value = result.pagination.total;
  } catch (error) {
    notifyError(error, "加载租户失败");
  } finally {
    tableLoading.value = false;
  }
}

async function loadPage(): Promise<void> {
  loading.value = true;
  try {
    if (props.mode === "global") {
      await loadTenantRows();
      return;
    }
    await loadTenantCatalog();
    await loadUnits();
  } catch (error) {
    notifyError(error, "加载组织管理数据失败");
  } finally {
    loading.value = false;
  }
}

async function loadUnits(): Promise<void> {
  if (!activeTenantId.value) {
    units.value = [];
    expandedUnitIds.value = [];
    return;
  }
  try {
    units.value = await listOrganizationUnits(activeTenantId.value);
    const parentIds = new Set(
      units.value
        .map((unit) => unit.parent_id)
        .filter((parentId): parentId is string => Boolean(parentId)),
    );
    const retained = expandedUnitIds.value.filter((unitId) => parentIds.has(unitId));
    expandedUnitIds.value = retained.length ? retained : Array.from(parentIds);
  } catch (error) {
    units.value = [];
    expandedUnitIds.value = [];
    notifyError(error, "加载组织管理数据失败");
  }
}

async function selectTenant(tenantId: string): Promise<void> {
  syncTenantContext(tenantId);
  if (activeTenantId.value === tenantId) return;
  activeTenantId.value = tenantId;
  expandedUnitIds.value = [];
  await loadUnits();
}

function syncTenantContext(tenantId: string): void {
  const scope =
    scopeStore.currentTenantOptions.find(
      (item) => item.scope_tenant_id === tenantId,
    ) ?? null;
  if (scope && scopeStore.currentTenantId !== tenantId) {
    scopeStore.setCurrentTenantScope(scope);
  }
}

function toggleUnitExpanded(unit: OrganizationTableRow): void {
  if (!unit.has_children) return;
  expandedUnitIds.value = expandedUnitIds.value.includes(unit.id)
    ? expandedUnitIds.value.filter((unitId) => unitId !== unit.id)
    : [...expandedUnitIds.value, unit.id];
}

async function openTenantOrganization(tenant: ManagedTenant): Promise<void> {
  await scopeStore.fetchCatalog();
  syncTenantContext(tenant.id);
  await router.push("/org");
}

async function submitTenantSearch(): Promise<void> {
  tenantPage.value = 1;
  await loadTenantRows();
}

async function changeTenantPage(page: number): Promise<void> {
  tenantPage.value = page;
  await loadTenantRows();
}

function resetTenantSearch(): void { tenantSearch.value = ""; void submitTenantSearch(); }

function openCreateTenant(): void {
  Object.assign(tenantForm, { tenantCode: "", tenantName: "", status: "active" });
  editingTenantId.value = "";
  drawerMode.value = "tenant-create";
}

function openEditTenant(tenant: ManagedTenant): void {
  editingTenantId.value = tenant.id;
  Object.assign(tenantForm, {
    tenantCode: tenant.tenant_code,
    tenantName: tenant.tenant_name,
    status: tenant.status,
  });
  drawerMode.value = "tenant-edit";
}

function openCreateUnit(parentId = ""): void {
  if (!activeTenant.value) return;
  editingUnitId.value = "";
  Object.assign(unitForm, {
    parentId,
    externalKey: "",
    name: "",
    unitType: "",
    metadataText: "{}",
    status: "active",
    sortOrder: 0,
  });
  drawerMode.value = "unit-create";
}

function openEditUnit(unit: ManagedOrganizationUnit): void {
  editingUnitId.value = unit.id;
  Object.assign(unitForm, {
    parentId: unit.parent_id ?? "",
    externalKey: unit.external_key,
    name: unit.name,
    unitType: unit.unit_type,
    metadataText: JSON.stringify(unit.metadata ?? {}, null, 2),
    status: unit.status,
    sortOrder: unit.sort_order,
  });
  drawerMode.value = "unit-edit";
}

async function saveDrawer(): Promise<void> {
  if (!drawerMode.value || saving.value) return;
  saving.value = true;
  try {
    if (drawerMode.value === "tenant-create") {
      if (!tenantForm.tenantCode.trim()) throw new Error("请填写租户编码");
      if (!tenantForm.tenantName.trim()) throw new Error("请填写租户名称");
      await createOrgTenant({
        tenantCode: tenantForm.tenantCode.trim(),
        tenantName: tenantForm.tenantName.trim(),
        status: tenantForm.status,
      });
      tenantPage.value = 1;
      await Promise.all([scopeStore.fetchCatalog(), loadTenantRows()]);
    } else if (drawerMode.value === "tenant-edit" && editingTenant.value) {
      if (!tenantForm.tenantName.trim()) throw new Error("请填写租户名称");
      await updateOrgTenant(editingTenant.value.id, {
        tenantName: tenantForm.tenantName.trim(),
        status: tenantForm.status,
      });
      await Promise.all([scopeStore.fetchCatalog(), loadTenantRows()]);
    } else {
      const metadata = parseMetadata();
      if (!unitForm.externalKey.trim()) throw new Error("请填写外部标识");
      if (!unitForm.name.trim()) throw new Error("请填写组织名称");
      if (drawerMode.value === "unit-create") {
        const created = await createOrganizationUnit({
          tenantId: activeTenantId.value,
          parentId: unitForm.parentId || null,
          externalKey: unitForm.externalKey.trim(),
          name: unitForm.name.trim(),
          unitType: unitForm.unitType.trim(),
          metadata,
          status: unitForm.status,
          sortOrder: Number(unitForm.sortOrder) || 0,
        });
      } else if (editingUnit.value) {
        await updateOrganizationUnit(editingUnit.value.id, {
          parentId: unitForm.parentId || null,
          name: unitForm.name.trim(),
          unitType: unitForm.unitType.trim(),
          metadata,
          status: unitForm.status,
          sortOrder: Number(unitForm.sortOrder) || 0,
        });
      }
      await loadUnits();
    }
    drawerMode.value = null;
    ElMessage.success("保存成功");
  } catch (error) {
    notifyError(error, "保存失败");
  } finally {
    saving.value = false;
  }
}

async function removeTenant(tenant: ManagedTenant): Promise<void> {
  try {
    await ElMessageBox.confirm(
      "确定删除租户“" + (tenant.tenant_name || tenant.tenant_code) + "”吗？",
      "删除租户",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  try {
    await deleteOrgTenant(tenant.id);
    if (activeTenantId.value === tenant.id) activeTenantId.value = "";
    await Promise.all([scopeStore.fetchCatalog(), loadTenantRows()]);
    ElMessage.success("租户已删除");
  } catch (error) {
    notifyError(error, "删除租户失败");
  }
}

async function removeUnit(unit: ManagedOrganizationUnit): Promise<void> {
  try {
    await ElMessageBox.confirm(
      "确定删除组织单元“" + (unit.name || unit.external_key) + "”吗？",
      "删除组织单元",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  try {
    await deleteOrganizationUnit(unit.id);
    await loadUnits();
    ElMessage.success("组织单元已删除");
  } catch (error) {
    notifyError(error, "删除组织单元失败");
  }
}

function parseMetadata(): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(unitForm.metadataText || "{}");
    if (!value || Array.isArray(value) || typeof value !== "object") throw new Error();
    return value as Record<string, unknown>;
  } catch {
    throw new Error("元数据必须是合法的 JSON 对象");
  }
}

function collectDescendants(parentId: string, result: Set<string>): void {
  for (const child of units.value.filter((unit) => unit.parent_id === parentId)) {
    result.add(child.id);
    collectDescendants(child.id, result);
  }
}

function childCount(unitId: string): number {
  return units.value.filter((unit) => unit.parent_id === unitId).length;
}

function parentNameById(unitId: string): string {
  const unit = units.value.find((item) => item.id === unitId);
  return unit?.name || unit?.external_key || "当前组织";
}

function closeDrawer(): void {
  if (!saving.value) drawerMode.value = null;
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(date);
}

function notifyError(error: unknown, fallback: string): void {
  ElMessage.error(error instanceof ApiError || error instanceof Error ? error.message : fallback);
}

watch(
  () => scopeStore.currentTenantId,
  async (tenantId) => {
    if (props.mode !== "tenant" || !tenantId || tenantId === activeTenantId.value) return;
    await selectTenant(tenantId);
  },
);

onMounted(loadPage);
</script>

<template>
  <div
    class="org-page organization-page"
    :class="{ 'is-global-mode': mode === 'global' }"
    v-loading="loading"
  >
    <header v-if="mode === 'tenant'" class="organization-local-head">
      <div>
        <h1>组织管理</h1>
        <p>维护当前租户的组织层级与基础信息。</p>
      </div>
    </header>

    <section class="organization-surface">
      <header class="organization-primary-toolbar global-resource-toolbar">
        <div
          v-if="canManageTenants"
          class="organization-section-tabs global-resource-title"
        >
          <h2>租户管理</h2>
        </div>
        <div v-else class="organization-view-title">
          <h2>组织管理</h2>
        </div>

        <div v-if="activeSection === 'tenants'" class="organization-toolbar-tools global-resource-tools">
          <div class="global-resource-filters">
          <el-input
            v-model="tenantSearch"
            class="organization-search"
            :prefix-icon="Search"
            placeholder="搜索租户名称或编码"
            clearable
            @keydown.enter="submitTenantSearch"
            @clear="submitTenantSearch"
          />
          <el-button :icon="RotateCcw" :disabled="tableLoading" @click="resetTenantSearch">重置</el-button>
          <el-button :icon="Search" type="primary" :disabled="tableLoading" @click="submitTenantSearch">搜索</el-button>
          </div>
          <div class="global-resource-actions">
          <el-button type="primary" :icon="CirclePlus" @click="openCreateTenant">
            新建租户
          </el-button>
          </div>
        </div>

        <div v-else class="organization-toolbar-tools">
          <el-button
            v-if="canManageOrganization"
            type="primary"
            :icon="CirclePlus"
            :disabled="!activeTenant"
            @click="openCreateUnit('')"
          >
            新建组织单元
          </el-button>
        </div>
      </header>

      <div
        v-if="activeSection === 'tenants'"
        class="organization-table-region global-resource-table-region"
      >
        <el-table
          v-loading="tableLoading"
          class="tenant-management-table organization-data-table global-resource-table"
          :data="tenantRows"
          row-key="id"
          height="100%"
        >
          <el-table-column label="租户" min-width="300">
            <template #default="{ row: tenant }">
              <div class="tenant-identity">
                <el-icon><OfficeBuilding /></el-icon>
                <span>
                  <strong>{{ tenant.tenant_name || tenant.tenant_code }}</strong>
                  <small>{{ tenant.tenant_code }}</small>
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="150">
            <template #default="{ row: tenant }">
              <el-tag :type="tenant.status === 'active' ? 'success' : 'info'">{{ tenant.status === "active" ? "启用" : "停用" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="190">
            <template #default="{ row: tenant }">{{ formatDate(tenant.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" min-width="220" align="right" fixed="right">
            <template #default="{ row: tenant }">
              <div class="row-actions global-resource-row-actions">
                <el-button type="primary" link @click="openTenantOrganization(tenant)">
                  管理组织
                </el-button>
                <el-button link @click="openEditTenant(tenant)">编辑</el-button>
                <el-button type="danger" link @click="removeTenant(tenant)">删除</el-button>
              </div>
            </template>
          </el-table-column>
          <template #empty>
            <ManagementEmptyState
              :title="tenantSearch.trim() ? '未找到匹配的租户' : '暂无租户'"
              :description="tenantSearch.trim() ? '请调整搜索条件后重试。' : '新建租户后，可在组织管理中维护组织层级。'"
            >
              <el-button v-if="!tenantSearch.trim()" type="primary" @click="openCreateTenant">
                创建第一个租户
              </el-button>
            </ManagementEmptyState>
          </template>
        </el-table>
          <el-pagination
            v-if="tenantTotal > 0"
            class="admin-pagination"
            layout="total, prev, pager, next"
            :current-page="tenantPage"
            :page-size="TENANT_PAGE_SIZE"
            :total="tenantTotal"
            @current-change="changeTenantPage"
          />
      </div>

      <div v-else class="organization-table-region">
        <el-table
          v-if="activeTenant"
          class="organization-tree-table organization-data-table"
          :data="organizationRows"
          row-key="id"
          height="100%"
        >
          <el-table-column label="组织名称" min-width="300">
            <template #default="{ row: unit }">
              <div
                class="organization-name"
                :style="{ paddingLeft: unit.tree_depth * 28 + 'px' }"
              >
                <button
                  v-if="unit.has_children"
                  type="button"
                  class="organization-tree-toggle"
                  :class="{ expanded: expandedUnitIds.includes(unit.id) }"
                  :aria-label="expandedUnitIds.includes(unit.id) ? '收起下级组织' : '展开下级组织'"
                  @click.stop="toggleUnitExpanded(unit)"
                >
                  <el-icon><ArrowRight /></el-icon>
                </button>
                <span v-else class="organization-tree-toggle-spacer" />
                <el-icon class="organization-unit-icon"><OfficeBuilding /></el-icon>
                <strong>{{ unit.name || unit.external_key }}</strong>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="150">
            <template #default="{ row: unit }">{{ unit.unit_type || "未分类" }}</template>
          </el-table-column>
          <el-table-column label="外部标识" min-width="180" prop="external_key" />
          <el-table-column label="直属下级" width="120" align="center">
            <template #default="{ row: unit }">{{ childCount(unit.id) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row: unit }">
              <span class="status-text" :class="unit.status">
                <i />
                {{ unit.status === "active" ? "启用" : "停用" }}
              </span>
            </template>
          </el-table-column>
          <el-table-column v-if="canManageOrganization" label="操作" width="260" align="right">
            <template #default="{ row: unit }">
              <div class="row-actions">
                <el-button type="primary" link @click.stop="openCreateUnit(unit.id)">
                  添加下级
                </el-button>
                <el-button link @click.stop="openEditUnit(unit)">编辑</el-button>
                <el-button type="danger" link @click.stop="removeUnit(unit)">删除</el-button>
              </div>
            </template>
          </el-table-column>
          <template #empty>
            <div class="organization-empty">
              <el-empty
                description="尚未创建组织单元"
                :image-size="92"
              />
              <el-button
                v-if="canManageOrganization"
                type="primary"
                :icon="CirclePlus"
                @click="openCreateUnit('')"
              >
                创建第一个组织单元
              </el-button>
            </div>
          </template>
        </el-table>

        <div v-else class="organization-empty no-tenant-empty">
          <el-empty description="先创建租户，再创建组织单元" :image-size="104" />
          <el-button
            v-if="canManageTenants"
            type="primary"
            :icon="CirclePlus"
            @click="openCreateTenant"
          >
            创建第一个租户
          </el-button>
        </div>

        <footer v-if="activeTenant && units.length" class="organization-table-footer">
          <span>共 {{ units.length }} 个组织单元</span>
        </footer>
      </div>
    </section>

    <FormDrawer
      :open="drawerMode !== null"
      :title="drawerTitle"
      :subtitle="drawerSubtitle"
      :saving="saving"
      @close="closeDrawer"
      @submit="saveDrawer"
    >
      <el-form
        v-if="drawerMode?.startsWith('tenant')"
        class="organization-drawer-form"
        label-position="top"
      >
        <el-form-item label="租户编码" required>
          <el-input
            v-model="tenantForm.tenantCode"
            :disabled="drawerMode === 'tenant-edit'"
            placeholder="唯一且创建后不可修改"
          />
        </el-form-item>
        <el-form-item label="租户名称" required>
          <el-input v-model="tenantForm.tenantName" placeholder="企业或业务空间名称" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="tenantForm.status">
            <el-option value="active" label="启用" />
            <el-option value="inactive" label="停用" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-form v-else class="organization-drawer-form" label-position="top">
        <el-form-item label="上级组织">
          <el-select v-model="unitForm.parentId" clearable filterable placeholder="作为根组织">
            <el-option
              v-for="unit in parentOptions"
              :key="unit.id"
              :label="unit.name || unit.external_key"
              :value="unit.id"
            />
          </el-select>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="外部标识" required>
              <el-input
                v-model="unitForm.externalKey"
                :disabled="drawerMode === 'unit-edit'"
                placeholder="例如 sales-east"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="组织名称" required>
              <el-input v-model="unitForm.name" placeholder="例如华东销售部" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="组织类型">
              <el-input v-model="unitForm.unitType" placeholder="部门、区域或项目组" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="排序">
              <el-input-number v-model="unitForm.sortOrder" :min="0" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="元数据（JSON）">
          <el-input
            v-model="unitForm.metadataText"
            type="textarea"
            :rows="5"
            placeholder="{ }"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="unitForm.status">
            <el-option value="active" label="启用" />
            <el-option value="inactive" label="停用" />
          </el-select>
        </el-form-item>
      </el-form>
    </FormDrawer>
  </div>
</template>

<style scoped>
.organization-page {
  --organization-control-height: 2rem;
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}

.organization-local-head {
  display: flex;
  min-height: 72px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  border: 1px solid rgba(215, 222, 226, 0.9);
  border-bottom: 0;
  padding: 14px 24px;
}

.organization-local-head h1,
.organization-local-head p {
  margin: 0;
}

.organization-local-head h1 {
  font-size: 18px;
}

.organization-local-head p {
  margin-top: 3px;
  color: var(--text-secondary);
  font-size: 12px;
}

.organization-surface {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(215, 222, 226, 0.9);
  background: #fff;
}

.organization-page.is-global-mode .organization-surface {
  border: 0;
}

.organization-primary-toolbar {
  display: flex;
  min-height: 3.75rem;
  flex: 0 0 auto;
  align-items: center;
  gap: 1rem;
  border-bottom: 1px solid rgba(219, 222, 234, 0.92);
  padding: 0.75rem 1.25rem;
}

.organization-view-title {
  display: flex;
  min-width: 9.75rem;
  align-items: center;
  gap: 0.75rem;
}

.organization-view-title h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 0.9375rem;
  font-weight: 780;
  white-space: nowrap;
}

.organization-section-tabs {
  display: flex;
  align-self: stretch;
  flex: 0 0 auto;
  align-items: stretch;
  gap: 1.5rem;
}

.organization-section-tabs h2 {
  align-self: center;
  margin: 0;
  color: var(--text-primary);
  font-size: 0.9375rem;
  font-weight: 780;
  white-space: nowrap;
}

.organization-section-tabs button {
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

.organization-section-tabs button:hover,
.organization-section-tabs button.active {
  color: var(--accent);
}

.organization-section-tabs button.active::after {
  position: absolute;
  right: 0;
  bottom: -0.75rem;
  left: 0;
  height: 2px;
  border-radius: 999px;
  background: var(--accent);
  content: "";
}

.organization-toolbar-tools {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  align-items: center;
  gap: 0.625rem;
}

.organization-toolbar-tools > .el-button {
  min-width: 7.75rem;
  height: var(--organization-control-height);
  min-height: var(--organization-control-height);
  margin-left: auto;
  padding-inline: 0.875rem;
}

.organization-page.is-global-mode .organization-toolbar-tools {
  justify-content: flex-end;
}

.organization-page.is-global-mode .organization-toolbar-tools > .el-button {
  min-width: auto;
  margin-left: 0;
}

.organization-page.is-global-mode .organization-toolbar-tools > .el-button:last-child {
  min-width: 7.75rem;
}

.organization-page.is-global-mode .organization-search {
  width: 240px;
}

.organization-search {
  width: clamp(14rem, 22vw, 22rem);
}

.organization-search :deep(.el-input__wrapper) {
  min-height: var(--organization-control-height);
  border-radius: var(--el-border-radius-base);
  box-shadow: 0 0 0 1px rgba(205, 209, 224, 0.95) inset;
}

.organization-table-region {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}

.organization-data-table {
  flex: 1 1 auto;
  --el-table-border-color: rgba(220, 223, 234, 0.92);
  --el-table-header-bg-color: #fbfbfd;
  --el-table-row-hover-bg-color: #f8f7ff;
}

.organization-data-table :deep(.el-table__inner-wrapper::before) {
  display: none;
}

.organization-data-table :deep(th.el-table__cell) {
  height: 2.875rem;
  background: #fbfbfd;
  color: #59586d;
  font-size: 0.8125rem;
  font-weight: 760;
}

.organization-data-table :deep(td.el-table__cell) {
  height: 3.25rem;
  color: #3f3e54;
  font-size: 0.8125rem;
}

.organization-data-table :deep(.cell) {
  padding-right: 0.875rem;
  padding-left: 0.875rem;
}

.tenant-identity,
.organization-name {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.5rem;
}

.tenant-identity > .el-icon,
.organization-unit-icon {
  flex: 0 0 auto;
  color: #4f46e5;
  font-size: 1.125rem;
}

.tenant-identity strong,
.tenant-identity small {
  display: block;
}

.tenant-identity strong,
.organization-name strong {
  color: #29283d;
  font-weight: 720;
}

.tenant-identity small {
  margin-top: 3px;
  color: var(--text-tertiary);
  font-size: 11px;
}

.organization-tree-toggle {
  display: inline-flex;
  width: 20px;
  height: 28px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  padding: 0;
  color: #56556d;
  transition: transform 140ms ease;
}

.organization-tree-toggle.expanded {
  transform: rotate(90deg);
}

.organization-tree-toggle-spacer {
  width: 20px;
  flex: 0 0 auto;
}

.row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.status-text {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text-primary);
}

.status-text i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #a4a4b2;
}

.status-text.active i {
  background: #16a05d;
}

.organization-empty {
  display: grid;
  min-height: 100%;
  place-items: center;
  align-content: center;
  padding: 2rem;
}

.organization-empty :deep(.el-empty) {
  padding-bottom: 10px;
}

.no-tenant-empty {
  flex: 1 1 auto;
}

.organization-table-footer {
  display: flex;
  min-height: 3rem;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid rgba(220, 223, 234, 0.92);
  padding: 0.5rem 1.25rem;
  color: var(--text-secondary);
  font-size: 0.8125rem;
}

.organization-drawer-form {
  width: 100%;
}

.organization-drawer-form :deep(.el-form-item) {
  margin-bottom: 1rem;
}

.organization-drawer-form :deep(.el-form-item__label) {
  padding-bottom: 0.375rem;
  color: var(--text-secondary);
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1.3;
}

.organization-drawer-form :deep(.el-select),
.organization-drawer-form :deep(.el-input-number) {
  width: 100%;
}

@media (max-width: 1040px) {
  .organization-primary-toolbar {
    min-height: auto;
    align-items: flex-start;
    flex-direction: column;
    gap: 14px;
  }

  .organization-toolbar-tools {
    width: 100%;
    flex-wrap: wrap;
  }

  .organization-toolbar-tools > .el-button {
    margin-left: 0;
  }

  .organization-search {
    width: min(420px, 100%);
  }

}

@media (max-width: 680px) {
  .organization-primary-toolbar {
    padding: 18px;
  }

  .organization-toolbar-tools {
    align-items: stretch;
    flex-direction: column;
  }

  .organization-search,
  .organization-toolbar-tools > .el-button {
    width: 100%;
  }
}
</style>
