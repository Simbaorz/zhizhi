<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  CirclePlus,
  Connection,
  Delete,
  EditPen,
  OfficeBuilding,
  Refresh,
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
import AppPanel from "@/components/AppPanel.vue";
import type { ManagedOrganizationUnit, ManagedTenant } from "@/types/admin";

interface OrganizationTreeNode extends ManagedOrganizationUnit {
  children: OrganizationTreeNode[];
}

type DrawerMode = "tenant-create" | "tenant-edit" | "unit-create" | "unit-edit";

const loading = ref(false);
const saving = ref(false);
const tenants = ref<ManagedTenant[]>([]);
const tenantTotal = ref(0);
const tenantPage = ref(1);
const tenantSearch = ref("");
const activeTenantId = ref("");
const units = ref<ManagedOrganizationUnit[]>([]);
const activeUnitId = ref("");
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

const activeTenant = computed(() =>
  tenants.value.find((tenant) => tenant.id === activeTenantId.value) ?? null,
);
const activeUnit = computed(() =>
  units.value.find((unit) => unit.id === activeUnitId.value) ?? null,
);
const drawerTitle = computed(() => ({
  "tenant-create": "新建租户",
  "tenant-edit": "编辑租户",
  "unit-create": "新建组织单元",
  "unit-edit": "编辑组织单元",
})[drawerMode.value ?? "tenant-create"]);

const organizationTree = computed<OrganizationTreeNode[]>(() => {
  const map = new Map(
    units.value.map((unit) => [unit.id, { ...unit, children: [] } as OrganizationTreeNode]),
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
        || (left.name || left.external_key).localeCompare(right.name || right.external_key, "zh-CN"),
    );
    nodes.forEach((node) => sort(node.children));
  };
  sort(roots);
  return roots;
});

const parentOptions = computed(() => {
  const blocked = new Set<string>();
  if (drawerMode.value === "unit-edit" && activeUnit.value) {
    collectDescendants(activeUnit.value.id, blocked);
    blocked.add(activeUnit.value.id);
  }
  return units.value.filter((unit) => !blocked.has(unit.id));
});

async function loadTenants(): Promise<void> {
  loading.value = true;
  try {
    const result = await listOrgTenantPage({
      page: tenantPage.value,
      pageSize: 50,
      search: tenantSearch.value.trim(),
      status: "all",
    });
    tenants.value = result.items;
    tenantTotal.value = result.pagination.total;
    if (!tenants.value.some((tenant) => tenant.id === activeTenantId.value)) {
      activeTenantId.value = tenants.value[0]?.id ?? "";
    }
    await loadUnits();
  } catch (error) {
    notifyError(error, "加载租户失败");
  } finally {
    loading.value = false;
  }
}

async function loadUnits(): Promise<void> {
  if (!activeTenantId.value) {
    units.value = [];
    activeUnitId.value = "";
    return;
  }
  try {
    units.value = await listOrganizationUnits(activeTenantId.value);
    if (!units.value.some((unit) => unit.id === activeUnitId.value)) {
      activeUnitId.value = units.value[0]?.id ?? "";
    }
  } catch (error) {
    units.value = [];
    notifyError(error, "加载组织树失败");
  }
}

async function selectTenant(tenantId: string): Promise<void> {
  if (activeTenantId.value === tenantId) return;
  activeTenantId.value = tenantId;
  activeUnitId.value = "";
  await loadUnits();
}

function openCreateTenant(): void {
  Object.assign(tenantForm, { tenantCode: "", tenantName: "", status: "active" });
  drawerMode.value = "tenant-create";
}

function openEditTenant(): void {
  if (!activeTenant.value) return;
  Object.assign(tenantForm, {
    tenantCode: activeTenant.value.tenant_code,
    tenantName: activeTenant.value.tenant_name,
    status: activeTenant.value.status,
  });
  drawerMode.value = "tenant-edit";
}

function openCreateUnit(parentId = ""): void {
  if (!activeTenant.value) return;
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

function openEditUnit(): void {
  if (!activeUnit.value) return;
  Object.assign(unitForm, {
    parentId: activeUnit.value.parent_id ?? "",
    externalKey: activeUnit.value.external_key,
    name: activeUnit.value.name,
    unitType: activeUnit.value.unit_type,
    metadataText: JSON.stringify(activeUnit.value.metadata ?? {}, null, 2),
    status: activeUnit.value.status,
    sortOrder: activeUnit.value.sort_order,
  });
  drawerMode.value = "unit-edit";
}

async function saveDrawer(): Promise<void> {
  if (!drawerMode.value || saving.value) return;
  saving.value = true;
  try {
    if (drawerMode.value === "tenant-create") {
      if (!tenantForm.tenantCode.trim()) throw new Error("请填写租户编码");
      const created = await createOrgTenant({ ...tenantForm });
      await loadTenants();
      activeTenantId.value = created.id;
      await loadUnits();
    } else if (drawerMode.value === "tenant-edit" && activeTenant.value) {
      await updateOrgTenant(activeTenant.value.id, {
        tenantName: tenantForm.tenantName.trim(),
        status: tenantForm.status,
      });
      await loadTenants();
    } else {
      const metadata = parseMetadata();
      if (!unitForm.externalKey.trim()) throw new Error("请填写外部标识");
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
        await loadUnits();
        activeUnitId.value = created.id;
      } else if (activeUnit.value) {
        await updateOrganizationUnit(activeUnit.value.id, {
          parentId: unitForm.parentId || null,
          name: unitForm.name.trim(),
          unitType: unitForm.unitType.trim(),
          metadata,
          status: unitForm.status,
          sortOrder: Number(unitForm.sortOrder) || 0,
        });
        await loadUnits();
      }
    }
    drawerMode.value = null;
    ElMessage.success("保存成功");
  } catch (error) {
    notifyError(error, "保存失败");
  } finally {
    saving.value = false;
  }
}

async function removeTenant(): Promise<void> {
  if (!activeTenant.value) return;
  await ElMessageBox.confirm(
    `确定删除租户“${activeTenant.value.tenant_name || activeTenant.value.tenant_code}”吗？`,
    "删除租户",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
  );
  try {
    await deleteOrgTenant(activeTenant.value.id);
    await loadTenants();
    ElMessage.success("租户已删除");
  } catch (error) {
    notifyError(error, "删除租户失败");
  }
}

async function removeUnit(): Promise<void> {
  if (!activeUnit.value) return;
  await ElMessageBox.confirm(
    `确定删除组织单元“${activeUnit.value.name || activeUnit.value.external_key}”吗？`,
    "删除组织单元",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
  );
  try {
    await deleteOrganizationUnit(activeUnit.value.id);
    await loadUnits();
    ElMessage.success("组织单元已删除");
  } catch (error) {
    notifyError(error, "删除组织单元失败");
  }
}

function parseMetadata(): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(unitForm.metadataText || "{}");
    if (!value || Array.isArray(value) || typeof value !== "object") {
      throw new Error();
    }
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

function notifyError(error: unknown, fallback: string): void {
  ElMessage.error(error instanceof ApiError || error instanceof Error ? error.message : fallback);
}

onMounted(loadTenants);
</script>

<template>
  <div class="organization-page" v-loading="loading">
    <AppPanel class="page-intro">
      <div>
        <span class="eyebrow">IDENTITY & ACCESS</span>
        <h1>组织架构</h1>
        <p>以租户为安全边界，按企业真实结构构建任意深度的组织树。</p>
      </div>
      <el-button :icon="Refresh" circle aria-label="刷新" @click="loadTenants" />
    </AppPanel>

    <section class="organization-workbench">
      <AppPanel class="tenant-panel">
        <div class="panel-heading">
          <div>
            <span class="panel-kicker">TENANTS</span>
            <strong>租户</strong>
          </div>
          <el-button type="primary" :icon="CirclePlus" circle @click="openCreateTenant" />
        </div>
        <el-input
          v-model="tenantSearch"
          :prefix-icon="Search"
          placeholder="搜索租户"
          clearable
          @keydown.enter="loadTenants"
          @clear="loadTenants"
        />
        <div class="tenant-list">
          <button
            v-for="tenant in tenants"
            :key="tenant.id"
            class="tenant-row"
            :class="{ active: tenant.id === activeTenantId }"
            type="button"
            @click="selectTenant(tenant.id)"
          >
            <span class="tenant-avatar">{{ (tenant.tenant_name || tenant.tenant_code).slice(0, 1) }}</span>
            <span>
              <strong>{{ tenant.tenant_name || tenant.tenant_code }}</strong>
              <small>{{ tenant.tenant_code }}</small>
            </span>
            <i :class="tenant.status" />
          </button>
          <el-empty v-if="tenants.length === 0" description="暂无租户" :image-size="64" />
        </div>
        <small class="tenant-count">共 {{ tenantTotal }} 个租户</small>
      </AppPanel>

      <AppPanel class="tree-panel">
        <div class="panel-heading">
          <div>
            <span class="panel-kicker">ORGANIZATION TREE</span>
            <strong>{{ activeTenant?.tenant_name || "请选择租户" }}</strong>
          </div>
          <el-button
            type="primary"
            :icon="CirclePlus"
            :disabled="!activeTenant"
            @click="openCreateUnit('')"
          >新建根节点</el-button>
        </div>
        <el-tree
          v-if="organizationTree.length"
          class="organization-tree"
          :data="organizationTree"
          node-key="id"
          default-expand-all
          highlight-current
          :current-node-key="activeUnitId"
          :props="{ label: 'name', children: 'children' }"
          @node-click="(node: OrganizationTreeNode) => (activeUnitId = node.id)"
        >
          <template #default="{ data }">
            <span class="tree-node">
              <span class="tree-node-icon"><el-icon><Connection /></el-icon></span>
              <span>
                <strong>{{ data.name || data.external_key }}</strong>
                <small>{{ data.unit_type || "未分类" }} · {{ data.external_key }}</small>
              </span>
              <el-tag v-if="data.status !== 'active'" type="info" size="small">停用</el-tag>
            </span>
          </template>
        </el-tree>
        <el-empty v-else description="尚未创建组织单元" />
      </AppPanel>

      <AppPanel class="detail-panel">
        <template v-if="activeUnit">
          <div class="detail-symbol"><el-icon><OfficeBuilding /></el-icon></div>
          <span class="panel-kicker">SELECTED UNIT</span>
          <h2>{{ activeUnit.name || activeUnit.external_key }}</h2>
          <p>{{ activeUnit.unit_type || "未设置组织类型" }}</p>
          <dl>
            <div><dt>外部标识</dt><dd>{{ activeUnit.external_key }}</dd></div>
            <div><dt>状态</dt><dd>{{ activeUnit.status === "active" ? "启用" : "停用" }}</dd></div>
            <div><dt>排序</dt><dd>{{ activeUnit.sort_order }}</dd></div>
            <div><dt>子节点</dt><dd>{{ units.filter((unit) => unit.parent_id === activeUnit?.id).length }}</dd></div>
          </dl>
          <div class="detail-actions">
            <el-button type="primary" :icon="CirclePlus" @click="openCreateUnit(activeUnit.id)">添加下级</el-button>
            <el-button :icon="EditPen" @click="openEditUnit">编辑</el-button>
            <el-button type="danger" plain :icon="Delete" @click="removeUnit">删除</el-button>
          </div>
        </template>
        <template v-else-if="activeTenant">
          <div class="detail-symbol"><el-icon><OfficeBuilding /></el-icon></div>
          <span class="panel-kicker">TENANT</span>
          <h2>{{ activeTenant.tenant_name || activeTenant.tenant_code }}</h2>
          <p>{{ activeTenant.tenant_code }}</p>
          <div class="detail-actions">
            <el-button :icon="EditPen" @click="openEditTenant">编辑租户</el-button>
            <el-button type="danger" plain :icon="Delete" @click="removeTenant">删除租户</el-button>
          </div>
        </template>
        <el-empty v-else description="选择一个租户开始配置" />
      </AppPanel>
    </section>

    <el-drawer v-model="drawerMode" :title="drawerTitle" size="460px" destroy-on-close>
      <el-form v-if="drawerMode?.startsWith('tenant')" label-position="top">
        <el-form-item label="租户编码" required>
          <el-input v-model="tenantForm.tenantCode" :disabled="drawerMode === 'tenant-edit'" />
        </el-form-item>
        <el-form-item label="租户名称"><el-input v-model="tenantForm.tenantName" /></el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="tenantForm.status">
            <el-radio-button value="active">启用</el-radio-button>
            <el-radio-button value="inactive">停用</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <el-form v-else label-position="top">
        <el-form-item label="上级组织">
          <el-select v-model="unitForm.parentId" clearable filterable placeholder="作为根节点">
            <el-option
              v-for="unit in parentOptions"
              :key="unit.id"
              :label="unit.name || unit.external_key"
              :value="unit.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="外部标识" required>
          <el-input v-model="unitForm.externalKey" :disabled="drawerMode === 'unit-edit'" placeholder="例如 sales-east" />
        </el-form-item>
        <el-form-item label="名称"><el-input v-model="unitForm.name" /></el-form-item>
        <el-form-item label="类型"><el-input v-model="unitForm.unitType" placeholder="部门、区域、项目组等" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="unitForm.sortOrder" :min="0" /></el-form-item>
        <el-form-item label="元数据（JSON）">
          <el-input v-model="unitForm.metadataText" type="textarea" :rows="6" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="unitForm.status">
            <el-radio-button value="active">启用</el-radio-button>
            <el-radio-button value="inactive">停用</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="drawerMode = null">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveDrawer">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.organization-page { display: grid; gap: 18px; min-width: 0; }
.page-intro { display: flex; align-items: center; justify-content: space-between; padding: 22px 26px; background: linear-gradient(115deg, #fff 55%, #f0edff); }
.eyebrow, .panel-kicker { display: block; color: #6366f1; font-size: 11px; font-weight: 800; letter-spacing: .14em; }
.page-intro h1 { margin: 6px 0 4px; color: #201f3b; font-size: 24px; }
.page-intro p { margin: 0; color: #73738d; }
.organization-workbench { display: grid; grid-template-columns: 260px minmax(360px, 1fr) 300px; gap: 16px; min-height: 630px; }
.tenant-panel, .tree-panel, .detail-panel { padding: 20px; overflow: hidden; }
.panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
.panel-heading strong { display: block; margin-top: 4px; color: #24223c; font-size: 16px; }
.tenant-list { display: grid; gap: 8px; margin: 14px 0; max-height: 510px; overflow: auto; }
.tenant-row { display: grid; grid-template-columns: 36px 1fr 8px; align-items: center; gap: 10px; width: 100%; padding: 10px; border: 1px solid transparent; border-radius: 12px; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.tenant-row:hover { background: #f5f3ff; }
.tenant-row.active { border-color: #c7c5ff; background: #eeecff; box-shadow: inset 3px 0 #6366f1; }
.tenant-avatar { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 10px; background: linear-gradient(135deg, #5b5bd6, #8b5cf6); color: #fff; font-weight: 800; }
.tenant-row strong, .tenant-row small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tenant-row small, .tenant-count { color: #8a8aa0; font-size: 11px; }
.tenant-row i { width: 7px; height: 7px; border-radius: 50%; background: #a8a8b8; }
.tenant-row i.active { background: #38bdf8; box-shadow: 0 0 0 4px #e0f5ff; }
.organization-tree { --el-tree-node-hover-bg-color: #f3f1ff; background: transparent; }
.organization-tree :deep(.el-tree-node__content) { height: auto; min-height: 52px; align-items: center; border-radius: 10px; }
.organization-tree :deep(.el-tree-node__expand-icon) { flex: 0 0 auto; }
.tree-node { display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 6px; }
.tree-node-icon { display: grid; width: 30px; height: 30px; place-items: center; border-radius: 9px; background: #eeecff; color: #5b5bd6; }
.tree-node > span:nth-child(2) { min-width: 0; }
.tree-node strong, .tree-node small { display: block; }
.tree-node strong, .tree-node small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-node small { margin-top: 2px; color: #8b8ba1; font-size: 11px; }
.tree-node .el-tag { margin-left: auto; }
.detail-panel { background: linear-gradient(160deg, #fff, #f7f5ff); }
.detail-symbol { display: grid; width: 52px; height: 52px; margin-bottom: 22px; place-items: center; border-radius: 15px; background: linear-gradient(135deg, #4f46e5, #8b5cf6); color: #fff; font-size: 24px; box-shadow: 0 12px 26px rgba(91, 91, 214, .25); }
.detail-panel h2 { margin: 7px 0 5px; color: #23213c; }
.detail-panel > p { margin: 0 0 24px; color: #85859a; }
.detail-panel dl { display: grid; gap: 1px; overflow: hidden; border: 1px solid #e6e3f2; border-radius: 12px; background: #e6e3f2; }
.detail-panel dl div { display: flex; justify-content: space-between; gap: 20px; padding: 12px; background: rgba(255, 255, 255, .88); }
.detail-panel dt { color: #85859a; }
.detail-panel dd { margin: 0; color: #363451; font-weight: 600; }
.detail-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; }
@media (max-width: 1180px) { .organization-workbench { grid-template-columns: 230px 1fr; } .detail-panel { grid-column: 1 / -1; min-height: 260px; } }
@media (max-width: 760px) { .organization-workbench { grid-template-columns: 1fr; } .tenant-panel, .tree-panel, .detail-panel { min-height: auto; } }
</style>
