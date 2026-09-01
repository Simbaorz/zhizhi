<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { storeToRefs } from "pinia";
import { Delete as Trash2, Edit as Pencil, Key, Plus, Refresh as RotateCcw, Search } from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";

import AppPanel from "@/components/AppPanel.vue";
import FieldInput from "@/components/FieldInput.vue";
import FormDrawer from "@/components/FormDrawer.vue";
import FormModal from "@/components/FormModal.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import StatusBanner from "@/components/StatusBanner.vue";
import { useRoleAdminStore } from "@/stores/roleAdmin";
import { useUiStore } from "@/stores/ui";
import type { AdminPermission, AdminRole } from "@/types/rbac";
import { formatDate } from "@/utils/format";

interface PermissionGroup {
  module: string;
  label: string;
  permissions: AdminPermission[];
}

const ROLE_PAGE_SIZE = 10;
const statusFilterOptions = [
  { label: "全部", value: "all" },
  { label: "启用", value: "active" },
  { label: "停用", value: "inactive" },
] as const;

const roleAdminStore = useRoleAdminStore();
const uiStore = useUiStore();

const roleRefs = storeToRefs(roleAdminStore);
const drawerMode = ref<"create" | "edit" | "permissions" | null>(null);
const selectedRole = ref<AdminRole | null>(null);
const selectedPermissionIds = ref<string[]>([]);
const keyword = ref("");
const searchInput = ref("");
const statusFilter = ref<"all" | "active" | "inactive">("all");
const statusInput = ref<"all" | "active" | "inactive">("all");
const rolePage = ref(1);
const roleListRefreshing = ref(false);
const permissionModuleLabels: Record<string, string> = {
  org: "组织管理",
  accounts: "账号管理",
  users: "账号管理",
  roles: "角色管理",
  admins: "账号管理",
  llm: "模型管理",
  scene_git: "场景 Git 授权",
  data_source: "数据源",
  skills: "技能管理",
  scenes: "业务场景管理",
  system: "系统权限",
};

async function confirmDanger(message: string): Promise<boolean> {
  try {
    await ElMessageBox.confirm(message, "确认操作", {
      confirmButtonText: "确认",
      cancelButtonText: "取消",
      type: "warning",
    });
    return true;
  } catch {
    return false;
  }
}
const permissionModuleOrder = [
  "org",
  "accounts",
  "users",
  "roles",
  "admins",
  "llm",
  "scene_git",
  "data_source",
  "skills",
  "scenes",
];
const roleForm = reactive({
  roleCode: "",
  roleName: "",
  description: "",
  status: "active",
  isDelegable: true,
});

const groupedPermissions = computed<PermissionGroup[]>(() => {
  const groups = new Map<string, typeof roleRefs.permissions.value>();
  for (const permission of roleRefs.permissions.value) {
    const key = permission.module || "system";
    groups.set(key, [...(groups.get(key) ?? []), permission]);
  }
  return Array.from(groups.entries())
    .sort(([firstModule], [secondModule]) => {
      const firstIndex = permissionModuleOrder.indexOf(firstModule);
      const secondIndex = permissionModuleOrder.indexOf(secondModule);
      if (firstIndex === -1 && secondIndex === -1) {
        return firstModule.localeCompare(secondModule);
      }
      return (firstIndex === -1 ? Number.MAX_SAFE_INTEGER : firstIndex)
        - (secondIndex === -1 ? Number.MAX_SAFE_INTEGER : secondIndex);
    })
    .map(([module, permissions]) => ({
      module,
      label: permissionModuleLabels[module] || module,
      permissions,
    }));
});

const drawerTitle = computed(() => {
  if (drawerMode.value === "create") {
    return "新建角色";
  }
  if (drawerMode.value === "edit") {
    return "编辑角色";
  }
  if (drawerMode.value === "permissions") {
    return "分配权限点";
  }
  return "";
});

const filteredRoles = computed(() => roleRefs.roles.value);
const hasSubmittedRoleFilters = computed(
  () => keyword.value.trim().length > 0 || statusFilter.value !== "all",
);
const roleEmptyTitle = computed(() => (hasSubmittedRoleFilters.value ? "没有匹配的角色" : "暂无角色"));
const roleEmptyBody = computed(() =>
  hasSubmittedRoleFilters.value
    ? "请调整搜索关键字或状态筛选。"
    : "系统只初始化 admin 超级管理员账号；其他角色请按实际管理职责手动创建。",
);
const rolePageCount = computed(() =>
  Math.max(1, Math.ceil(roleRefs.pagination.value.total / ROLE_PAGE_SIZE)),
);
const permissionTotal = computed(() => roleRefs.permissions.value.length);
const permissionDialogSubtitle = computed(() => {
  if (!selectedRole.value) {
    return "";
  }
  return `${selectedRole.value.role_name} / ${selectedRole.value.role_code}`;
});

async function refresh(): Promise<void> {
  roleListRefreshing.value = true;
  try {
    await Promise.all([
      roleAdminStore.loadRoles({
        search: keyword.value,
        status: statusFilter.value,
        page: rolePage.value,
        pageSize: ROLE_PAGE_SIZE,
      }),
      roleAdminStore.loadPermissions(),
    ]);
    if (rolePage.value > rolePageCount.value && roleRefs.pagination.value.total > 0) {
      rolePage.value = rolePageCount.value;
      await roleAdminStore.loadRoles({
        search: keyword.value,
        status: statusFilter.value,
        page: rolePage.value,
        pageSize: ROLE_PAGE_SIZE,
      });
    }
  } finally {
    roleListRefreshing.value = false;
  }
}

async function submitSearch(): Promise<void> {
  if (roleListRefreshing.value) {
    return;
  }
  keyword.value = searchInput.value.trim();
  searchInput.value = keyword.value;
  statusFilter.value = statusInput.value;
  rolePage.value = 1;
  await refresh();
}

async function resetSearch(): Promise<void> {
  if (roleListRefreshing.value) {
    return;
  }
  keyword.value = "";
  searchInput.value = "";
  statusFilter.value = "all";
  statusInput.value = "all";
  rolePage.value = 1;
  await refresh();
}

function setStatusFilter(status: "all" | "active" | "inactive"): void {
  statusInput.value = status;
}

async function setRolePage(page: number): Promise<void> {
  rolePage.value = Math.min(Math.max(page, 1), rolePageCount.value);
  await refresh();
}

function openCreate(): void {
  selectedRole.value = null;
  roleForm.roleCode = "";
  roleForm.roleName = "";
  roleForm.description = "";
  roleForm.status = "active";
  roleForm.isDelegable = true;
  drawerMode.value = "create";
}

function openEdit(role: AdminRole): void {
  selectedRole.value = role;
  roleForm.roleCode = role.role_code;
  roleForm.roleName = role.role_name;
  roleForm.description = role.description;
  roleForm.status = role.status;
  roleForm.isDelegable = role.is_delegable ?? true;
  drawerMode.value = "edit";
}

async function openPermissions(role: AdminRole): Promise<void> {
  selectedRole.value = role;
  await Promise.all([
    roleAdminStore.loadPermissions(),
    roleAdminStore.loadRolePermissionSet(role.id),
  ]);
  selectedPermissionIds.value = roleRefs.selectedRolePermissions.value.map(
    (permission) => permission.id,
  );
  drawerMode.value = "permissions";
}

function closeDrawer(): void {
  drawerMode.value = null;
  selectedRole.value = null;
  selectedPermissionIds.value = [];
}

function permissionGroupSelectedCount(group: PermissionGroup): number {
  const selectedIds = new Set(selectedPermissionIds.value);
  return group.permissions.filter((permission) => selectedIds.has(permission.id)).length;
}

function isPermissionGroupChecked(group: PermissionGroup): boolean {
  return group.permissions.length > 0 && permissionGroupSelectedCount(group) === group.permissions.length;
}

function isPermissionGroupIndeterminate(group: PermissionGroup): boolean {
  const selectedCount = permissionGroupSelectedCount(group);
  return selectedCount > 0 && selectedCount < group.permissions.length;
}

function syncPermissionSelection(nextSelectedIds: Set<string>): void {
  selectedPermissionIds.value = roleRefs.permissions.value
    .map((permission) => permission.id)
    .filter((permissionId) => nextSelectedIds.has(permissionId));
}

function handlePermissionGroupCheck(group: PermissionGroup, checked: string | number | boolean): void {
  const nextSelectedIds = new Set(selectedPermissionIds.value);
  for (const permission of group.permissions) {
    if (checked) {
      nextSelectedIds.add(permission.id);
    } else {
      nextSelectedIds.delete(permission.id);
    }
  }
  syncPermissionSelection(nextSelectedIds);
}

function selectAllPermissions(): void {
  selectedPermissionIds.value = roleRefs.permissions.value.map((permission) => permission.id);
}

function clearPermissions(): void {
  selectedPermissionIds.value = [];
}

async function submitDrawer(): Promise<void> {
  try {
    if (drawerMode.value === "create") {
      await roleAdminStore.createNewRole({
        roleCode: roleForm.roleCode.trim(),
        roleName: roleForm.roleName.trim(),
        description: roleForm.description.trim(),
        status: roleForm.status,
        isDelegable: roleForm.isDelegable,
      });
      uiStore.pushNotice({ tone: "success", title: "角色已创建" });
    } else if (drawerMode.value === "edit" && selectedRole.value) {
      await roleAdminStore.patchRole(selectedRole.value.id, {
        roleName: roleForm.roleName.trim(),
        description: roleForm.description.trim(),
        status: roleForm.status,
        isDelegable: roleForm.isDelegable,
      });
      uiStore.pushNotice({ tone: "success", title: "角色已更新" });
    } else if (drawerMode.value === "permissions" && selectedRole.value) {
      await roleAdminStore.saveRolePermissionSet(selectedRole.value.id, selectedPermissionIds.value);
      uiStore.pushNotice({ tone: "success", title: "权限点已更新" });
    }
    closeDrawer();
    await refresh();
  } catch {
    uiStore.pushNotice({ tone: "danger", title: roleRefs.errorMessage.value || "角色操作失败" });
  }
}

async function deleteRole(role: AdminRole): Promise<void> {
  if (!await confirmDanger(`确认删除角色「${role.role_name}」吗？删除后会同步移除用户角色和角色权限绑定。`)) {
    return;
  }
  try {
    await roleAdminStore.removeRole(role.id);
    uiStore.pushNotice({ tone: "warning", title: "角色已删除" });
    await refresh();
  } catch {
    uiStore.pushNotice({ tone: "danger", title: roleRefs.errorMessage.value || "删除角色失败" });
  }
}

onMounted(async () => {
  await refresh();
});
</script>

<template>
  <div class="roles-page">
    <AppPanel class="roles-table-card">
      <header class="roles-toolbar">
        <div class="roles-toolbar-copy">
          <h2>角色与权限</h2>
        </div>

        <div class="roles-toolbar-actions admin-toolbar-layout">
          <div class="admin-filter-group">
            <el-input
              v-model="searchInput"
              class="admin-toolbar-search"
              type="search"
              placeholder="搜索角色编码 / 名称"
              clearable
              @keydown.enter.prevent="submitSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-segmented
              v-model="statusInput"
              :options="statusFilterOptions"
              aria-label="状态筛选"
            />
            <el-button :icon="RotateCcw" :disabled="roleListRefreshing" @click="resetSearch">
              重置
            </el-button>
            <el-button type="primary" :icon="Search" :disabled="roleListRefreshing" @click="submitSearch">
              搜索
            </el-button>
          </div>
          <div class="admin-action-group">
            <el-button type="primary" :icon="Plus" @click="openCreate">新建角色</el-button>
          </div>
        </div>
      </header>

      <LoadingBlock v-if="roleListRefreshing" />
      <StatusBanner
        v-else-if="roleRefs.errorMessage.value"
        tone="danger"
        title="角色数据加载失败"
        :body="roleRefs.errorMessage.value"
      />
      <div v-else class="admin-table-region">
        <el-table
          class="admin-data-table"
          :data="filteredRoles"
          height="100%"
          row-key="id"
          stripe
        >
          <el-table-column label="角色" min-width="220">
            <template #default="{ row: role }">
              <el-space alignment="center">
                <el-avatar :size="32">{{ role.role_name.slice(0, 1).toUpperCase() }}</el-avatar>
                <span class="roles-name-cell">
                  <span>
                    <strong>{{ role.role_name }}</strong>
                    <small>{{ role.role_code }}</small>
                  </span>
                </span>
              </el-space>
            </template>
          </el-table-column>
          <el-table-column label="状态" min-width="100">
            <template #default="{ row: role }">
              <el-tag :type="role.status === 'active' ? 'success' : 'info'" effect="light">
                {{ role.status === "active" ? "启用" : "停用" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="描述" min-width="220" show-overflow-tooltip>
            <template #default="{ row: role }">
              {{ role.description || "无描述" }}
            </template>
          </el-table-column>
          <el-table-column label="更新时间" min-width="160">
            <template #default="{ row: role }">
              {{ role.updated_at ? formatDate(role.updated_at) : "暂无记录" }}
            </template>
          </el-table-column>
          <el-table-column label="操作" align="right" min-width="170">
            <template #default="{ row: role }">
              <el-space :size="8">
                <el-button link type="primary" :icon="Key" @click="openPermissions(role)">权限</el-button>
                <el-button link type="primary" :icon="Pencil" @click="openEdit(role)">编辑</el-button>
                <el-button link type="danger" :icon="Trash2" :disabled="roleRefs.saving.value" @click="deleteRole(role)">删除</el-button>
              </el-space>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty :description="roleEmptyTitle">
              <span class="admin-empty-description">{{ roleEmptyBody }}</span>
            </el-empty>
          </template>
        </el-table>
      </div>
      <el-pagination
        v-if="!roleListRefreshing && roleRefs.pagination.value.total > 0"
        class="admin-pagination"
        :current-page="rolePage"
        :page-size="ROLE_PAGE_SIZE"
        :total="roleRefs.pagination.value.total"
        layout="total, prev, pager, next"
        @current-change="setRolePage"
      />
    </AppPanel>

    <FormDrawer
      :open="drawerMode === 'create' || drawerMode === 'edit'"
      :title="drawerTitle"
      :subtitle="selectedRole?.role_code"
      :saving="roleRefs.saving.value"
      @close="closeDrawer"
      @submit="submitDrawer"
    >
      <div v-if="drawerMode === 'create' || drawerMode === 'edit'" class="grid gap-4">
        <FieldInput
          v-model="roleForm.roleCode"
          label="角色编码"
          placeholder="skill_editor"
          :disabled="drawerMode === 'edit'"
        />
        <FieldInput v-model="roleForm.roleName" label="角色名称" placeholder="内容管理员" />
        <label class="grid gap-1 text-xs font-medium text-secondary-text">
          <span>描述</span>
          <el-input
            v-model="roleForm.description"
            type="textarea"
            :autosize="{ minRows: 4 }"
          />
        </label>
        <label class="grid gap-1 text-xs font-medium text-secondary-text">
          <span>状态</span>
          <el-select v-model="roleForm.status" size="default">
            <el-option value="active" label="启用" />
            <el-option value="inactive" label="停用" />
          </el-select>
        </label>
        <label class="roles-delegation-setting">
          <span class="roles-delegation-copy">
            <strong>角色分配限制</strong>
            <small>
              {{
                roleForm.isDelegable
                  ? "有账号管理授权权限的人，可在自己的管理范围内分配此角色。"
                  : "仅超级管理员可以分配此角色。"
              }}
            </small>
          </span>
          <el-switch v-model="roleForm.isDelegable" class="roles-delegation-input" />
        </label>
      </div>
    </FormDrawer>

    <FormModal
      :open="drawerMode === 'permissions'"
      title="分配权限点"
      :subtitle="permissionDialogSubtitle"
      :saving="roleRefs.saving.value"
      submit-text="保存权限"
      size="wide"
      @close="closeDrawer"
      @submit="submitDrawer"
    >
      <div class="roles-permission-dialog">
        <section class="roles-permission-summary">
          <div class="roles-permission-role">
            <el-avatar class="roles-permission-avatar" shape="square">
              <el-icon><Key /></el-icon>
            </el-avatar>
            <div class="roles-permission-role-copy">
              <strong>{{ selectedRole?.role_name || "未选择角色" }}</strong>
              <small>{{ selectedRole?.description || "为该角色选择可使用的后台功能权限。" }}</small>
            </div>
          </div>

          <div class="roles-permission-actions">
            <el-tag type="success" effect="light">
              已选 {{ selectedPermissionIds.length }} / {{ permissionTotal }}
            </el-tag>
            <el-button native-type="button" :disabled="permissionTotal === 0" @click="selectAllPermissions">
              全选
            </el-button>
            <el-button native-type="button" :disabled="selectedPermissionIds.length === 0" @click="clearPermissions">
              清空
            </el-button>
          </div>
        </section>

        <el-empty
          v-if="groupedPermissions.length === 0"
          description="暂无可分配权限点"
        />
        <section v-else class="roles-permission-groups">
          <el-card
            v-for="group in groupedPermissions"
            :key="group.module"
            class="roles-permission-group"
            shadow="never"
          >
            <template #header>
              <div class="roles-permission-group-head">
                <el-checkbox
                  :model-value="isPermissionGroupChecked(group)"
                  :indeterminate="isPermissionGroupIndeterminate(group)"
                  @change="handlePermissionGroupCheck(group, $event)"
                >
                  <span class="roles-permission-group-title">{{ group.label }}</span>
                </el-checkbox>
                <el-tag effect="plain">
                  {{ permissionGroupSelectedCount(group) }} / {{ group.permissions.length }}
                </el-tag>
              </div>
            </template>

            <el-checkbox-group v-model="selectedPermissionIds" class="roles-permission-list">
              <el-checkbox
                v-for="permission in group.permissions"
                :key="permission.id"
                class="roles-permission-item"
                :value="permission.id"
                border
              >
                <span class="roles-permission-item-copy">
                  <strong>{{ permission.permission_name }}</strong>
                  <small>{{ permission.permission_code }}</small>
                  <em v-if="permission.description">{{ permission.description }}</em>
                </span>
              </el-checkbox>
            </el-checkbox-group>
          </el-card>
        </section>
      </div>
    </FormModal>
  </div>
</template>
