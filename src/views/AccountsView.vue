<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import { Edit, Key, Plus, Refresh, Search, Tickets, User as UserIcon } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import AppPanel from "@/components/AppPanel.vue";
import StatusBanner from "@/components/StatusBanner.vue";
import { useAdminTenantMemberStore } from "@/stores/adminTenantMember";
import { useAuthStore } from "@/stores/auth";
import { useScopeStore } from "@/stores/scope";
import { useUserAdminStore } from "@/stores/userAdmin";
import type { AdminScopeRef, ManagedUser } from "@/types/admin";
import { formatDate } from "@/utils/format";

type DialogMode = "create" | "edit" | "password" | "authorization";
type StatusFilter = "all" | "active" | "inactive";

const PAGE_SIZE = 20;
const authStore = useAuthStore();
const scopeStore = useScopeStore();
const userStore = useUserAdminStore();
const memberStore = useAdminTenantMemberStore();
const scopeRefs = storeToRefs(scopeStore);
const userRefs = storeToRefs(userStore);
const memberRefs = storeToRefs(memberStore);

const searchInput = ref("");
const search = ref("");
const statusInput = ref<StatusFilter>("all");
const status = ref<StatusFilter>("all");
const page = ref(1);
const dialogMode = ref<DialogMode | null>(null);
const selectedUser = ref<ManagedUser | null>(null);
const selectedAuthorizationScope = ref("");

const accountForm = reactive({
  username: "",
  password: "",
  displayName: "",
  phone: "",
  email: "",
  status: "active",
});
const passwordForm = reactive({ password: "" });
const authorizationForm = reactive({ roleIds: [] as string[] });

const permissionCodes = computed(() => new Set(authStore.permissionCodes));
const canCreate = computed(() => authStore.isSuper || permissionCodes.value.has("admins.create"));
const canEdit = computed(() => authStore.isSuper || permissionCodes.value.has("admins.update"));
const canResetPassword = computed(
  () => authStore.isSuper || permissionCodes.value.has("admins.reset_password"),
);
const canAssignRoles = computed(
  () => authStore.isSuper || permissionCodes.value.has("admins.assign_role"),
);
const currentTenantId = computed(() => scopeRefs.currentTenantId.value);
const currentManagementScope = computed<AdminScopeRef | null>(() => {
  const selected = scopeRefs.selectedScope.value;
  if (!selected || selected.scope_tenant_id !== currentTenantId.value) return null;
  return selected;
});
const pageCount = computed(() => Math.max(1, Math.ceil(userRefs.pagination.value.total / PAGE_SIZE)));
const authorizationScopes = computed(() => {
  const tenantId = currentTenantId.value;
  const seen = new Set<string>();
  return scopeRefs.nodes.value
    .filter((node) => node.scope.scope_tenant_id === tenantId)
    .filter((node) => {
      const key = scopeKey(node.scope);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((node) => ({ key: scopeKey(node.scope), label: node.label, scope: node.scope }));
});
const dialogTitle = computed(() => ({
  create: "新增管理员",
  edit: "编辑管理员",
  password: "重置管理员密码",
  authorization: "配置管理员权限",
})[dialogMode.value ?? "create"]);
const dialogSaving = computed(() => userRefs.saving.value || memberRefs.saving.value);

onMounted(async () => {
  if (scopeRefs.nodes.value.length === 0) await scopeStore.fetchCatalog();
  await loadUsers();
});

watch(currentTenantId, async () => {
  page.value = 1;
  closeDialog();
  await loadUsers();
});

async function loadUsers(): Promise<void> {
  const tenantId = currentTenantId.value;
  if (!tenantId) {
    userStore.reset();
    return;
  }
  await userStore.loadTenantAdmins(tenantId, {
    search: search.value,
    status: status.value,
    page: page.value,
    pageSize: PAGE_SIZE,
  });
  if (page.value > pageCount.value && userRefs.pagination.value.total > 0) {
    page.value = pageCount.value;
    await loadUsers();
  }
}

async function applyFilters(): Promise<void> {
  search.value = searchInput.value.trim();
  status.value = statusInput.value;
  page.value = 1;
  await loadUsers();
}

async function resetFilters(): Promise<void> {
  searchInput.value = "";
  search.value = "";
  statusInput.value = "all";
  status.value = "all";
  page.value = 1;
  await loadUsers();
}

function openCreate(): void {
  selectedUser.value = null;
  Object.assign(accountForm, {
    username: "",
    password: "",
    displayName: "",
    phone: "",
    email: "",
    status: "active",
  });
  dialogMode.value = "create";
}

function openEdit(user: ManagedUser): void {
  selectedUser.value = user;
  Object.assign(accountForm, {
    username: user.username,
    password: "",
    displayName: user.display_name,
    phone: user.phone ?? "",
    email: user.email ?? "",
    status: user.status,
  });
  dialogMode.value = "edit";
}

function openPassword(user: ManagedUser): void {
  selectedUser.value = user;
  passwordForm.password = "";
  dialogMode.value = "password";
}

async function openAuthorization(user: ManagedUser): Promise<void> {
  selectedUser.value = user;
  authorizationForm.roleIds = (user.roles ?? []).map((role) => role.role_id || role.id);
  const currentScope = user.scopes?.[0];
  selectedAuthorizationScope.value = currentScope
    ? scopeKey({
        scope_type: currentScope.scope_type,
        scope_tenant_id: currentScope.scope_tenant_id,
        scope_organization_unit_id: currentScope.scope_organization_unit_id,
      })
    : scopeKey(currentManagementScope.value!);
  await memberStore.load(currentManagementScope.value ?? undefined);
  dialogMode.value = "authorization";
}

function closeDialog(): void {
  dialogMode.value = null;
  selectedUser.value = null;
  passwordForm.password = "";
  authorizationForm.roleIds = [];
  selectedAuthorizationScope.value = "";
}

async function submitDialog(): Promise<void> {
  const scope = currentManagementScope.value;
  if (!scope || !dialogMode.value) return;
  if (dialogMode.value === "create") {
    if (!accountForm.username.trim()) return;
    await userStore.createTenantAdmin(scope, {
      username: accountForm.username.trim(),
      password: accountForm.password || undefined,
      displayName: accountForm.displayName.trim(),
      phone: accountForm.phone.trim() || undefined,
      email: accountForm.email.trim() || undefined,
      status: accountForm.status,
    });
    ElMessage.success("管理员已创建或绑定。后续可继续配置角色与管理范围。");
  } else if (dialogMode.value === "edit" && selectedUser.value) {
    await userStore.patchUser(
      selectedUser.value.id,
      {
        displayName: accountForm.displayName.trim(),
        phone: accountForm.phone.trim(),
        email: accountForm.email.trim(),
        status: accountForm.status,
      },
      scope,
    );
    ElMessage.success("管理员信息已更新。");
  } else if (dialogMode.value === "password" && selectedUser.value) {
    if (!passwordForm.password) return;
    await userStore.resetPassword(selectedUser.value.id, passwordForm.password, scope);
    ElMessage.success("管理员密码已重置。");
  } else if (dialogMode.value === "authorization" && selectedUser.value) {
    const selectedScope = authorizationScopes.value.find(
      (option) => option.key === selectedAuthorizationScope.value,
    )?.scope;
    if (!selectedScope || authorizationForm.roleIds.length === 0) return;
    await memberStore.replaceAuthorization(scope, {
      principalAdminUserId: selectedUser.value.id,
      roleIds: authorizationForm.roleIds,
      scopes: [selectedScope],
      status: "active",
    });
    ElMessage.success("管理员角色与管理范围已更新。");
  }
  closeDialog();
  await loadUsers();
}

function scopeKey(scope: AdminScopeRef): string {
  return [
    scope.scope_type,
    scope.scope_tenant_id,
    scope.scope_organization_unit_id ?? "",
  ].join("::");
}

function roleSummary(user: ManagedUser): string {
  const names = (user.roles ?? []).map((role) => role.role_name || role.role_code).filter(Boolean);
  return names.length > 0 ? names.join("、") : "未分配角色";
}

function scopeSummary(user: ManagedUser): string {
  const scope = user.scopes?.[0];
  if (!scope || scope.scope_type === "tenant") return "租户";
  const match = authorizationScopes.value.find((option) => option.key === scopeKey(scope));
  return match?.label ?? "组织单元";
}

function userInitial(value: string): string {
  return value.trim().slice(0, 1).toUpperCase() || "管";
}
</script>

<template>
  <div class="accounts-page">
    <AppPanel class="global-management-shell accounts-management-shell">
      <header class="global-management-head accounts-management-head">
        <el-space class="global-management-identity" alignment="center">
          <el-icon class="global-management-mark" aria-hidden="true">
            <UserIcon />
          </el-icon>
          <div class="global-management-title">
            <h2>账号管理</h2>
            <p>维护当前租户的后台管理员账号、角色与组织管理范围</p>
          </div>
        </el-space>
      </header>
    </AppPanel>

    <section class="accounts-section">
      <AppPanel class="accounts-card">
        <header class="accounts-card-header">
          <div class="accounts-card-title">
            <h3>管理员</h3>
          </div>
          <div class="accounts-card-actions admin-toolbar-layout">
            <div class="admin-filter-group">
              <el-input
                v-model="searchInput"
                class="admin-toolbar-search"
                type="search"
                clearable
                placeholder="搜索用户名、姓名、手机或邮箱"
                @keydown.enter.prevent="applyFilters"
              >
                <template #prefix><el-icon><Search /></el-icon></template>
              </el-input>
              <el-segmented
                v-model="statusInput"
                :options="[
                  { label: '全部', value: 'all' },
                  { label: '启用', value: 'active' },
                  { label: '停用', value: 'inactive' },
                ]"
                aria-label="状态筛选"
              />
              <el-button :icon="Refresh" :disabled="userRefs.loading.value" @click="resetFilters">重置</el-button>
              <el-button type="primary" :icon="Search" :disabled="userRefs.loading.value" @click="applyFilters">搜索</el-button>
            </div>
            <div class="admin-action-group">
              <el-button v-if="canCreate" type="primary" :icon="Plus" :disabled="!currentManagementScope" @click="openCreate">
                新增管理员
              </el-button>
            </div>
          </div>
        </header>

        <div v-if="scopeRefs.errorMessage.value" class="admin-table-region accounts-feedback-region">
          <StatusBanner tone="danger" title="管理范围加载失败" :body="scopeRefs.errorMessage.value" />
        </div>
        <div v-else-if="!currentTenantId" class="admin-table-region accounts-empty-region">
          <el-empty description="请先在顶部选择当前租户。" />
        </div>
        <div v-else-if="userRefs.errorMessage.value" class="admin-table-region accounts-feedback-region">
          <StatusBanner tone="danger" title="当前租户管理员加载失败" :body="userRefs.errorMessage.value" />
        </div>
        <div v-else class="admin-table-region">
          <el-table
            v-loading="userRefs.loading.value"
            class="admin-data-table"
            :data="userRefs.users.value"
            height="100%"
            stripe
            row-key="id"
          >
            <el-table-column label="账号" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <div class="accounts-user-cell">
                  <span class="accounts-avatar">{{ userInitial(row.display_name || row.username) }}</span>
                  <span>
                    <strong>{{ row.display_name || row.username }}</strong>
                    <small>{{ row.username }}<template v-if="row.is_super"> · 超级管理员</template></small>
                  </span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.status === 'active' ? 'success' : 'info'" effect="light">
                  {{ row.status === "active" ? "启用" : "停用" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="角色" min-width="150" show-overflow-tooltip>
              <template #default="{ row }"><strong>{{ roleSummary(row) }}</strong></template>
            </el-table-column>
            <el-table-column label="授权范围" min-width="150" show-overflow-tooltip>
              <template #default="{ row }"><strong>{{ scopeSummary(row) }}</strong></template>
            </el-table-column>
            <el-table-column label="最近登录" min-width="150">
              <template #default="{ row }">{{ row.last_login_time ? formatDate(row.last_login_time) : "暂无记录" }}</template>
            </el-table-column>
            <el-table-column label="操作" align="right" fixed="right" width="210">
              <template #default="{ row }">
                <el-space :size="10" wrap>
                  <el-button v-if="canAssignRoles" link type="primary" :icon="Tickets" @click="openAuthorization(row)">授权</el-button>
                  <el-button v-if="canResetPassword" link type="primary" :icon="Key" @click="openPassword(row)">密码</el-button>
                  <el-button v-if="canEdit" link type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
                </el-space>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty :description="search ? '没有匹配的管理员' : '暂无管理员'" />
            </template>
          </el-table>
        </div>

        <el-pagination
          v-if="currentTenantId && !userRefs.errorMessage.value && userRefs.pagination.value.total > 0"
          v-model:current-page="page"
          class="admin-pagination"
          :page-size="PAGE_SIZE"
          :total="userRefs.pagination.value.total"
          layout="total, prev, pager, next"
          @current-change="loadUsers"
        />
      </AppPanel>
    </section>

    <el-dialog :model-value="dialogMode !== null" :title="dialogTitle" width="min(560px, 92vw)" destroy-on-close @close="closeDialog">
      <StatusBanner v-if="memberRefs.errorMessage.value" tone="danger" title="权限保存失败" :body="memberRefs.errorMessage.value" />
      <el-form v-if="dialogMode === 'create' || dialogMode === 'edit'" label-position="top">
        <el-form-item label="用户名" required><el-input v-model="accountForm.username" :disabled="dialogMode === 'edit'" maxlength="64" /></el-form-item>
        <el-form-item v-if="dialogMode === 'create'" label="初始密码"><el-input v-model="accountForm.password" type="password" show-password autocomplete="new-password" placeholder="绑定已有管理员时可留空" /></el-form-item>
        <el-form-item label="显示名称"><el-input v-model="accountForm.displayName" maxlength="128" /></el-form-item>
        <div class="account-form-grid">
          <el-form-item label="手机"><el-input v-model="accountForm.phone" maxlength="32" /></el-form-item>
          <el-form-item label="邮箱"><el-input v-model="accountForm.email" maxlength="128" /></el-form-item>
        </div>
        <el-form-item label="状态"><el-select v-model="accountForm.status"><el-option label="启用" value="active" /><el-option label="停用" value="inactive" /></el-select></el-form-item>
      </el-form>
      <el-form v-else-if="dialogMode === 'password'" label-position="top">
        <el-alert title="密码重置后，该管理员已有登录会话将失效。" type="warning" :closable="false" show-icon />
        <el-form-item label="新密码" required class="dialog-field"><el-input v-model="passwordForm.password" type="password" show-password autocomplete="new-password" /></el-form-item>
      </el-form>
      <el-form v-else-if="dialogMode === 'authorization'" label-position="top">
        <StatusBanner v-if="memberRefs.assignableRoleErrorMessage.value" tone="danger" title="可分配角色加载失败" :body="memberRefs.assignableRoleErrorMessage.value" />
        <el-form-item label="角色" required>
          <el-select v-model="authorizationForm.roleIds" multiple filterable collapse-tags style="width: 100%">
            <el-option v-for="role in memberRefs.assignableRoles.value" :key="role.id" :label="role.role_name" :value="role.id" :disabled="role.status !== 'active'" />
          </el-select>
        </el-form-item>
        <el-form-item label="管理范围" required>
          <el-select v-model="selectedAuthorizationScope" filterable style="width: 100%">
            <el-option v-for="option in authorizationScopes" :key="option.key" :label="option.label" :value="option.key" />
          </el-select>
        </el-form-item>
        <el-alert title="管理员范围仅支持触点、省或市。" type="info" :closable="false" show-icon />
      </el-form>
      <template #footer>
        <el-button @click="closeDialog">取消</el-button>
        <el-button type="primary" :loading="dialogSaving" @click="submitDialog">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.account-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.dialog-field { margin-top: 18px; }
@media (max-width: 720px) {
  .account-form-grid { grid-template-columns: 1fr; gap: 0; }
}
</style>
