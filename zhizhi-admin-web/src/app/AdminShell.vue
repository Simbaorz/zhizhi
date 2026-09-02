<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch, type Component } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import {
  ArrowLeft as CollapseSidebarIcon,
  ArrowRight as ExpandSidebarIcon,
  Avatar,
  ArrowDown as ChevronDown,
  Checked as ShieldCheck,
  Connection,
  Cpu,
  DataAnalysis,
  DataBoard,
  HomeFilled,
  Key as KeyRound,
  Platform,
  Refresh as RefreshCw,
  Share,
  Setting as SettingIcon,
  SuitcaseLine,
  SwitchButton as LogOut,
  Tools,
  User as UserRound,
} from "@element-plus/icons-vue";
import { storeToRefs } from "pinia";

import assistantIconUrl from "@/assets/zhizhi-logo.png";
import AppPanel from "@/components/AppPanel.vue";
import EmptyState from "@/components/EmptyState.vue";
import NoticeStack from "@/components/NoticeStack.vue";
import { useAdminTenantMemberStore } from "@/stores/adminTenantMember";
import { useAuthStore } from "@/stores/auth";
import { useNavigationStore } from "@/stores/navigation";
import { useScopeStore } from "@/stores/scope";
import { useSceneStore } from "@/stores/scene";
import { useSkillStore } from "@/stores/skill";
import { useUiStore } from "@/stores/ui";
import type { AdminScopeRef } from "@/types/admin";
import type { AdminTenantScope } from "@/types/rbac";
import {
  scopeBreadcrumb,
  scopeDisplayLabel,
  scopeKey,
  tenantScopeDisplayLabel,
} from "@/utils/scope";
import { formatDate } from "@/utils/format";

const route = useRoute();
const router = useRouter();

const authStore = useAuthStore();
const navigationStore = useNavigationStore();
const scopeStore = useScopeStore();
const skillStore = useSkillStore();
const sceneStore = useSceneStore();
const tenantMemberStore = useAdminTenantMemberStore();
const uiStore = useUiStore();

const authRefs = storeToRefs(authStore);
const scopeRefs = storeToRefs(scopeStore);
const uiRefs = storeToRefs(uiStore);

type AccountPanelTab = "profile" | "password" | "permissions";
type AccountMenuCommand = "settings" | "logout";

const accountMenuCommand = {
  settings: "settings",
  logout: "logout",
} satisfies Record<AccountMenuCommand, AccountMenuCommand>;

const accountSettingsOpen = ref(false);
const accountPanelTab = ref<AccountPanelTab>("profile");
const accountSaving = ref(false);
const logoutConfirmOpen = ref(false);
const logoutPending = ref(false);
const profileForm = reactive({
  displayName: "",
  phone: "",
  email: "",
});
const passwordForm = reactive({
  currentPassword: "",
  newPassword: "",
  confirmPassword: "",
});
const sidebarTextVisible = ref(!uiRefs.sidebarCollapsed.value);
let sidebarTextTimer: number | undefined;

const isLoginRoute = computed(() => route.path === "/login");
function normalizedNavigationLabel(item: { key: string; label: string }): string {
  if (item.key === "skills") return "技能管理";
  if (item.key === "scenes") return "业务场景管理";
  return item.label;
}

const navigationItems = computed(() =>
  navigationStore.items
    .filter((item) => !["dashboard", "users"].includes(item.key))
    .map((item) => ({ ...item, label: normalizedNavigationLabel(item) })),
);
const navigationIcon: Record<string, Component> = {
  dashboard: HomeFilled,
  global: Platform,
  org: Connection,
  accounts: Avatar,
  models: Cpu,
  "scene-git": Share,
  "data-sources": DataAnalysis,
  users: UserRound,
  roles: ShieldCheck,
  skills: Tools,
  scenes: SuitcaseLine,
};
const sidebarToggleIcon = computed<Component>(() =>
  uiRefs.sidebarCollapsed.value ? ExpandSidebarIcon : CollapseSidebarIcon,
);
const pageTitle = computed(() => String(route.meta.title ?? "后台管理"));
const currentUserLabel = computed(
  () => authRefs.user.value?.display_name || authRefs.user.value?.username || "",
);
const currentUserInitial = computed(() => currentUserLabel.value.trim().slice(0, 1) || "管");
const currentUsername = computed(() => authRefs.user.value?.username || "");
const currentTenantLabel = computed(() => {
  const scope = scopeRefs.currentTenantScope.value;
  return scope ? tenantScopeDisplayLabel(scope, scopeRefs.nodes.value) : "未选择租户";
});
const activeBreadcrumbScope = computed(() => {
  if (route.path === "/skills" || route.path === "/scenes") {
    return scopeRefs.selectedAssetTenantScope.value;
  }
  return scopeRefs.selectedScope.value;
});
const breadcrumb = computed(() => scopeBreadcrumb(activeBreadcrumbScope.value, scopeRefs.nodes.value));
const topbarBreadcrumbItems = computed(() => [
  "后台管理",
  ...(breadcrumb.value.length > 0 ? breadcrumb.value : ["未选择租户"]),
  ...(pageTitle.value === "后台管理" ? [] : [pageTitle.value]),
]);
const accountRoleNames = computed(() =>
  authRefs.roles.value.map((role) => role.role_name || role.role_code),
);
const accountTenantSummary = computed(() => currentTenantLabel.value);
const accountLastLoginLabel = computed(() =>
  authRefs.user.value?.last_login_time ? formatDate(authRefs.user.value.last_login_time) : "暂无记录",
);
const sidebarWidth = computed(() =>
  uiRefs.sidebarCollapsed.value
    ? "var(--admin-sidebar-collapsed-width)"
    : "var(--admin-sidebar-width)",
);
const accountMemberRows = computed(() =>
  authRefs.tenantMembers.value.map((member) => {
    const tenantScope: AdminScopeRef = {
      scope_type: "tenant",
      scope_tenant_id: member.tenant_id,
      scope_organization_unit_id: "",
    };
    const roles = member.roles
      .map((role) =>
        role.role?.role_name
        || role.role_name
        || role.role?.role_code
        || role.role_code
        || `角色 ${role.role_id}`,
      )
      .filter(Boolean);
    const scopes = member.scopes
      .map((scope) => accountScopeLabel(scope))
      .filter(Boolean);
    return {
      key: member.id,
      tenant: tenantScopeDisplayLabel(tenantScope, scopeRefs.nodes.value),
      tenantId: member.tenant_id,
      status: member.status === "active" ? "启用" : "停用",
      roles: Array.from(new Set(roles)),
      scopes,
    };
  }),
);

function resetFeatureStores(): void {
  scopeStore.reset();
  skillStore.reset();
  sceneStore.reset();
  tenantMemberStore.reset();
}

async function refreshAll(): Promise<void> {
  await authStore.restoreSession();
  if (authStore.isAuthenticated) {
    await scopeStore.fetchCatalog();
  }
}

async function logout(): Promise<void> {
  resetAccountSettingsPanel();
  await authStore.logout();
  resetFeatureStores();
  await router.push("/login");
}

function requestLogout(): void {
  logoutConfirmOpen.value = true;
}

function cancelLogout(): void {
  if (logoutPending.value) {
    return;
  }
  logoutConfirmOpen.value = false;
}

async function confirmLogout(): Promise<void> {
  if (logoutPending.value) {
    return;
  }
  logoutPending.value = true;
  try {
    await logout();
  } finally {
    logoutPending.value = false;
  }
}

function resetAccountSettingsPanel(): void {
  accountSettingsOpen.value = false;
  logoutConfirmOpen.value = false;
  accountPanelTab.value = "profile";
  accountSaving.value = false;
  syncProfileForm();
  clearPasswordForm();
}

function syncProfileForm(): void {
  const user = authRefs.user.value;
  profileForm.displayName = user?.display_name ?? "";
  profileForm.phone = user?.phone ?? "";
  profileForm.email = user?.email ?? "";
}

function clearPasswordForm(): void {
  passwordForm.currentPassword = "";
  passwordForm.newPassword = "";
  passwordForm.confirmPassword = "";
}

function openAccountSettings(): void {
  syncProfileForm();
  clearPasswordForm();
  accountPanelTab.value = "profile";
  accountSettingsOpen.value = true;
}

function handleAccountCommand(command: string | number | object): void {
  if (command === "settings") {
    openAccountSettings();
    return;
  }
  if (command === "logout") {
    requestLogout();
  }
}

function toggleSidebar(): void {
  sidebarTextVisible.value = false;
  uiStore.toggleSidebarCollapsed();
}

async function navigateMobile(path: string): Promise<void> {
  await router.push(path);
  uiRefs.mobileSidebarOpen.value = false;
}

function closeAccountSettings(): void {
  if (logoutPending.value) {
    return;
  }
  logoutConfirmOpen.value = false;
  accountSettingsOpen.value = false;
}

function unlockPasswordInput(event: FocusEvent): void {
  const input = event.target;
  if (input instanceof HTMLInputElement) {
    input.removeAttribute("readonly");
  }
}

async function saveProfile(): Promise<void> {
  if (accountSaving.value) {
    return;
  }
  accountSaving.value = true;
  try {
    await authStore.updateProfile({
      displayName: profileForm.displayName.trim(),
      phone: profileForm.phone.trim(),
      email: profileForm.email.trim(),
    });
    uiStore.pushNotice({ tone: "success", title: "个人信息已更新" });
    syncProfileForm();
  } catch {
    uiStore.pushNotice({ tone: "danger", title: authRefs.errorMessage.value || "更新个人信息失败" });
  } finally {
    accountSaving.value = false;
  }
}

async function savePassword(): Promise<void> {
  if (accountSaving.value) {
    return;
  }
  if (!passwordForm.currentPassword || !passwordForm.newPassword) {
    uiStore.pushNotice({ tone: "danger", title: "请填写当前密码和新密码" });
    return;
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    uiStore.pushNotice({ tone: "danger", title: "两次输入的新密码不一致" });
    return;
  }
  accountSaving.value = true;
  try {
    await authStore.changePassword({
      currentPassword: passwordForm.currentPassword,
      newPassword: passwordForm.newPassword,
    });
    clearPasswordForm();
    accountSettingsOpen.value = false;
    uiStore.pushNotice({ tone: "success", title: "密码已更新，请使用新密码重新登录" });
    await router.replace("/login");
  } catch {
    uiStore.pushNotice({ tone: "danger", title: authRefs.errorMessage.value || "修改密码失败" });
  } finally {
    accountSaving.value = false;
  }
}

function accountScopeLabel(scopeItem: AdminTenantScope): string {
  const scope = tenantScopeFromItem(scopeItem);
  if (!scope) {
    return "";
  }
  const label = scopeLabel(scope);
  if (scope.scope_type === "tenant") {
    return `租户级：${label}`;
  }
  if (scope.scope_type === "organization_unit") {
    return `组织单元：${label}`;
  }
  return label;
}

function tenantScopeFromItem(scopeItem: AdminTenantScope): AdminScopeRef | null {
  if (scopeItem.scope) {
    return scopeItem.scope;
  }
  if (!scopeItem.scope_type || !scopeItem.scope_tenant_id) {
    return null;
  }
  return {
    scope_type: scopeItem.scope_type,
    scope_tenant_id: scopeItem.scope_tenant_id,
    scope_organization_unit_id: scopeItem.scope_organization_unit_id ?? "",
  };
}

function scopeLabel(scope: AdminScopeRef): string {
  const node = scopeRefs.nodes.value.find((item) => scopeKey(item.scope) === scopeKey(scope));
  if (scope.scope_type === "tenant") {
    return tenantScopeDisplayLabel(scope, scopeRefs.nodes.value);
  }
  return scopeDisplayLabel(scope, node?.label);
}

function selectCurrentTenant(tenantId: string): void {
  const nextScope =
    scopeRefs.currentTenantOptions.value.find((scope) => scope.scope_tenant_id === tenantId) ?? null;
  scopeStore.setCurrentTenantScope(nextScope);
}

function handleCurrentTenantChange(value: string | number | boolean): void {
  selectCurrentTenant(String(value));
}

watch(
  () => authRefs.user.value?.id,
  async (userId) => {
    if (!userId) {
      resetFeatureStores();
      return;
    }
    await scopeStore.fetchCatalog();
  },
  { immediate: true },
);

watch(
  () => uiRefs.sidebarCollapsed.value,
  (collapsed) => {
    if (sidebarTextTimer !== undefined) {
      window.clearTimeout(sidebarTextTimer);
      sidebarTextTimer = undefined;
    }
    if (collapsed) {
      sidebarTextVisible.value = false;
      return;
    }
    sidebarTextTimer = window.setTimeout(() => {
      sidebarTextVisible.value = true;
      sidebarTextTimer = undefined;
    }, 180);
  },
);

watch(
  () => scopeRefs.selectedAssetTenantScope.value,
  async (scope) => {
    if (!scope || !authStore.isAuthenticated) {
      return;
    }
    if (route.path === "/skills") {
      await skillStore.loadSkills(scope);
    } else if (route.path === "/scenes") {
      await Promise.all([sceneStore.loadScenes(scope), skillStore.loadSkills(scope)]);
    }
  },
);

watch(
  () => route.path,
  async (path) => {
    if (path === "/login") {
      resetAccountSettingsPanel();
      return;
    }
    if (!authStore.isAuthenticated) {
      return;
    }
    if (path === "/skills") {
      const scope = scopeRefs.selectedAssetTenantScope.value;
      if (!scope) {
        return;
      }
      await skillStore.loadSkills(scope);
    } else if (path === "/scenes") {
      const scope = scopeRefs.selectedAssetTenantScope.value;
      if (!scope) {
        return;
      }
      await Promise.all([sceneStore.loadScenes(scope), skillStore.loadSkills(scope)]);
    }
  },
  { immediate: true },
);

onMounted(async () => {
  if (!authStore.sessionChecked) {
    await refreshAll();
  }
});
</script>

<template>
  <NoticeStack />

  <RouterView v-if="isLoginRoute" />

  <el-container
    v-else
    class="admin-shell"
    :class="{
      'sidebar-collapsed': uiRefs.sidebarCollapsed.value,
      'sidebar-text-hidden': !sidebarTextVisible,
    }"
  >
    <el-aside class="admin-sidebar" :width="sidebarWidth">
      <RouterLink to="/" class="sidebar-brand">
        <img class="sidebar-logo" :src="assistantIconUrl" alt="致知" />
        <span v-if="sidebarTextVisible" class="sidebar-brand-text">
          <strong>致知</strong>
          <small>管理后台</small>
        </span>
      </RouterLink>

      <el-menu
        class="sidebar-menu app-scrollbar"
        :default-active="route.path"
        :collapse="uiRefs.sidebarCollapsed.value"
        :collapse-transition="false"
        router
      >
        <template v-if="uiRefs.sidebarCollapsed.value">
          <el-menu-item
            v-for="item in navigationItems"
            :key="item.key"
            :index="item.path"
            :aria-label="item.label"
          >
            <el-icon aria-hidden="true">
              <component :is="navigationIcon[item.key] ?? DataBoard" />
            </el-icon>
          </el-menu-item>
        </template>
        <template v-else>
          <el-menu-item
            v-for="item in navigationItems"
            :key="item.key"
            :index="item.path"
          >
            <el-icon aria-hidden="true">
              <component :is="navigationIcon[item.key] ?? DataBoard" />
            </el-icon>
            <template #title>
              <span class="sidebar-menu-label">{{ item.label }}</span>
            </template>
          </el-menu-item>
        </template>
      </el-menu>

      <el-button
        class="sidebar-collapse"
        text
        :aria-label="uiRefs.sidebarCollapsed.value ? '展开菜单' : '收起菜单'"
        @click="toggleSidebar"
      >
        <el-icon class="sidebar-collapse-icon" aria-hidden="true">
          <component :is="sidebarToggleIcon" />
        </el-icon>
        <span v-if="sidebarTextVisible" class="sidebar-collapse-label">
          收起菜单
        </span>
      </el-button>
    </el-aside>

    <el-container class="admin-workspace" direction="vertical">
      <el-header class="admin-topbar" height="var(--admin-header-height)">
        <div class="topbar-title">
          <el-breadcrumb class="topbar-breadcrumb" separator="/">
            <el-breadcrumb-item
              v-for="(item, index) in topbarBreadcrumbItems"
              :key="`${item}-${index}`"
            >
              {{ item }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <el-space class="topbar-actions" :size="12" alignment="center" wrap>
          <el-button class="topbar-menu-button" text @click="uiRefs.mobileSidebarOpen.value = !uiRefs.mobileSidebarOpen.value">
            菜单
          </el-button>
          <el-select
            :model-value="scopeRefs.currentTenantId.value"
            :disabled="scopeRefs.currentTenantOptions.value.length === 0"
            :title="currentTenantLabel"
            :placeholder="scopeRefs.currentTenantOptions.value.length === 0 ? '暂无可用租户' : '未选择租户'"
            class="topbar-tenant-select"
            size="small"
            @change="handleCurrentTenantChange"
          >
            <template #prefix>
              <span class="topbar-tenant-prefix">租户</span>
            </template>
            <el-option v-if="scopeRefs.currentTenantOptions.value.length === 0" value="" label="暂无可用租户" />
            <el-option
              v-for="scope in scopeRefs.currentTenantOptions.value"
              :key="scope.scope_tenant_id"
              :value="scope.scope_tenant_id"
              :label="tenantScopeDisplayLabel(scope, scopeRefs.nodes.value)"
            />
          </el-select>

          <el-tooltip content="刷新数据" placement="bottom">
            <el-button
              class="topbar-refresh-button"
              circle
              text
              :icon="RefreshCw"
              size="small"
              aria-label="刷新数据"
              @click="refreshAll"
            />
          </el-tooltip>

          <el-dropdown
            class="topbar-account-menu"
            trigger="click"
            placement="bottom-end"
            @command="handleAccountCommand"
          >
            <el-button class="topbar-account-trigger" text size="small">
              <el-avatar class="topbar-account-avatar" :size="26">
                {{ currentUserInitial }}
              </el-avatar>
              <span class="topbar-account-copy">
                <strong>{{ currentUserLabel }}</strong>
                <small>{{ currentUsername }}</small>
              </span>
              <el-icon class="topbar-account-chevron" aria-hidden="true">
                <ChevronDown />
              </el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu class="topbar-account-dropdown">
                <el-dropdown-item :command="accountMenuCommand.settings">
                  <el-icon><SettingIcon /></el-icon>
                  账号设置
                </el-dropdown-item>
                <el-dropdown-item :command="accountMenuCommand.logout" divided>
                  <el-icon><LogOut /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </el-space>
      </el-header>

      <el-dialog
        :model-value="accountSettingsOpen"
        class="account-profile-dialog"
        width="min(54rem, calc(100vw - 2rem))"
        append-to-body
        align-center
        :close-on-click-modal="!logoutPending"
        :close-on-press-escape="!logoutPending"
        @close="closeAccountSettings"
      >
        <template #header>
          <el-space class="account-profile-header" alignment="center" :size="12">
            <el-avatar class="account-profile-avatar" shape="square" :size="42">
              {{ currentUserInitial }}
            </el-avatar>
            <div class="account-profile-title">
              <h2>{{ currentUserLabel || "账号设置" }}</h2>
              <p>{{ currentUsername }} · 账号设置</p>
            </div>
          </el-space>
        </template>

        <el-row class="account-profile-layout" :gutter="18">
          <el-col :xs="24" :md="8" :lg="7">
            <el-card class="account-profile-card" shadow="never">
              <el-space class="account-profile-user" alignment="center" :size="10">
                <el-avatar class="account-profile-avatar" shape="square" :size="44">
                  {{ currentUserInitial }}
                </el-avatar>
                <span class="account-profile-user-copy" :title="`${currentUserLabel} / ${currentUsername}`">
                  <strong>{{ currentUserLabel }}</strong>
                  <small>{{ currentUsername }}</small>
                </span>
              </el-space>

              <el-descriptions class="account-profile-summary" :column="1" size="default" border>
                <el-descriptions-item label="角色">
                  {{ authStore.isSuper ? "超级管理员" : accountRoleNames.join("、") || "未分配角色" }}
                </el-descriptions-item>
                <el-descriptions-item label="当前触点">
                  {{ accountTenantSummary }}
                </el-descriptions-item>
                <el-descriptions-item label="最近登录">
                  {{ accountLastLoginLabel }}
                </el-descriptions-item>
              </el-descriptions>
            </el-card>
          </el-col>

          <el-col :xs="24" :md="16" :lg="17">
            <el-card class="account-profile-card account-profile-main" shadow="never">
              <el-tabs v-model="accountPanelTab" class="account-profile-tabs">
                <el-tab-pane name="profile">
                  <template #label>
                    <span class="account-profile-tab-label">
                      <el-icon><UserRound /></el-icon>
                      账号资料
                    </span>
                  </template>
                  <el-scrollbar class="account-profile-scrollbar">
                    <el-space class="account-profile-pane" direction="vertical" alignment="stretch" :size="16">
                      <el-text type="info">这些信息只影响当前登录身份展示，不会改变角色或管理范围。</el-text>
                      <el-form class="account-profile-form" label-position="top" size="default">
                        <el-form-item label="显示名称">
                          <el-input v-model="profileForm.displayName" placeholder="请输入显示名称" />
                        </el-form-item>
                        <el-form-item label="手机号">
                          <el-input v-model="profileForm.phone" type="tel" placeholder="未填写" />
                        </el-form-item>
                        <el-form-item label="邮箱">
                          <el-input v-model="profileForm.email" type="email" placeholder="未填写" />
                        </el-form-item>
                      </el-form>
                    </el-space>
                  </el-scrollbar>
                </el-tab-pane>

                <el-tab-pane name="password">
                  <template #label>
                    <span class="account-profile-tab-label">
                      <el-icon><KeyRound /></el-icon>
                      安全设置
                    </span>
                  </template>
                  <el-scrollbar class="account-profile-scrollbar">
                    <el-space class="account-profile-pane" direction="vertical" alignment="stretch" :size="16">
                      <el-alert
                        title="修改的是当前账号的全局登录密码，会影响该账号在所有触点的登录。建议使用至少 8 位且包含字母、数字的密码。"
                        type="info"
                        show-icon
                        :closable="false"
                      />
                      <el-form class="account-profile-form" label-position="top" size="default">
                        <el-form-item label="当前密码">
                          <el-input
                            v-model="passwordForm.currentPassword"
                            type="password"
                            name="account_current_password"
                            autocomplete="off"
                            readonly
                            show-password
                            @focus="unlockPasswordInput"
                          />
                        </el-form-item>
                        <el-form-item label="新密码">
                          <el-input
                            v-model="passwordForm.newPassword"
                            type="password"
                            name="account_new_password"
                            autocomplete="off"
                            readonly
                            show-password
                            @focus="unlockPasswordInput"
                          />
                        </el-form-item>
                        <el-form-item label="确认新密码">
                          <el-input
                            v-model="passwordForm.confirmPassword"
                            type="password"
                            name="account_confirm_password"
                            autocomplete="off"
                            readonly
                            show-password
                            @focus="unlockPasswordInput"
                          />
                        </el-form-item>
                      </el-form>
                    </el-space>
                  </el-scrollbar>
                </el-tab-pane>

                <el-tab-pane name="permissions">
                  <template #label>
                    <span class="account-profile-tab-label">
                      <el-icon><ShieldCheck /></el-icon>
                      权限范围
                    </span>
                  </template>
                  <el-scrollbar class="account-profile-scrollbar">
                    <el-space class="account-profile-pane" direction="vertical" alignment="stretch" :size="16">
                      <el-text type="info">只读查看，角色与范围不能在此处修改。</el-text>
                      <el-result
                        v-if="authStore.isSuper"
                        icon="success"
                        title="超级管理员"
                        sub-title="拥有全局管理权限，不受当前触点范围限制。"
                      />
                      <el-empty
                        v-else-if="accountMemberRows.length === 0"
                        description="当前账号没有启用中的触点角色与管理范围。"
                      />
                      <el-table v-else :data="accountMemberRows" size="default" class="account-profile-table">
                        <el-table-column label="租户" min-width="180">
                          <template #default="{ row }">
                            <span class="account-profile-table-cell">
                              <strong>{{ row.tenant }}</strong>
                              <small>{{ row.tenantId }}</small>
                            </span>
                          </template>
                        </el-table-column>
                        <el-table-column label="角色" min-width="180">
                          <template #default="{ row }">
                            <el-space wrap :size="6">
                              <el-tag v-for="role in row.roles" :key="role" type="primary" effect="light">
                                {{ role }}
                              </el-tag>
                              <span v-if="row.roles.length === 0">未分配角色</span>
                            </el-space>
                          </template>
                        </el-table-column>
                        <el-table-column label="管理范围" min-width="260">
                          <template #default="{ row }">
                            {{ row.scopes.length > 0 ? row.scopes.join("、") : "未配置范围" }}
                          </template>
                        </el-table-column>
                      </el-table>
                    </el-space>
                  </el-scrollbar>
                </el-tab-pane>
              </el-tabs>
            </el-card>
          </el-col>
        </el-row>

        <template #footer>
          <el-button :disabled="accountSaving" @click="closeAccountSettings">关闭</el-button>
          <el-button
            v-if="accountPanelTab === 'profile'"
            type="primary"
            :loading="accountSaving"
            @click="saveProfile"
          >
            保存资料
          </el-button>
          <el-button
            v-else-if="accountPanelTab === 'password'"
            type="primary"
            :loading="accountSaving"
            @click="savePassword"
          >
            更新密码
          </el-button>
        </template>
      </el-dialog>

      <el-dialog
        :model-value="logoutConfirmOpen"
        class="account-logout-confirm-dialog"
        width="min(28rem, calc(100vw - 2rem))"
        append-to-body
        :show-close="false"
        align-center
        :close-on-click-modal="!logoutPending"
        :close-on-press-escape="!logoutPending"
        @close="cancelLogout"
      >
        <template #header>
          <div class="account-logout-confirm-header">
            <el-icon class="account-logout-confirm-icon"><LogOut /></el-icon>
            <div>
              <h3>退出登录</h3>
              <p>确认要退出当前管理员账号吗？</p>
            </div>
          </div>
        </template>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="当前账号">
            {{ currentUserLabel }} {{ currentUsername }}
          </el-descriptions-item>
        </el-descriptions>
        <template #footer>
          <el-button :disabled="logoutPending" @click="cancelLogout">取消</el-button>
          <el-button type="danger" :loading="logoutPending" @click="confirmLogout">退出登录</el-button>
        </template>
      </el-dialog>

      <div v-if="uiRefs.mobileSidebarOpen.value" class="mobile-nav">
        <button
          v-for="item in navigationItems"
          :key="item.key"
          type="button"
          class="mobile-nav-link"
          :class="{ active: route.path === item.path }"
          @click="navigateMobile(item.path)"
        >
          {{ item.label }}
        </button>
      </div>

      <el-main class="admin-content">
        <AppPanel v-if="authRefs.loading.value" class="p-8">
          <EmptyState title="正在加载后台会话" body="正在恢复登录态和权限菜单。" />
        </AppPanel>
        <RouterView v-else />
      </el-main>
    </el-container>
  </el-container>
</template>
