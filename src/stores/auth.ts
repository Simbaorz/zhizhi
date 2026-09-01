import { computed, ref } from "vue";
import { defineStore } from "pinia";

import {
  changeAdminPassword,
  getAdminMe,
  loginAdmin,
  logoutAdmin,
  updateAdminProfile,
} from "@/api/admin";
import { ApiError } from "@/api/http";
import type { LoginResponse, LoginUser, MeResponse } from "@/types/auth";
import type {
  AdminPermission,
  AdminRole,
  AdminTenantMember,
  NavigationItem,
} from "@/types/rbac";

export const useAuthStore = defineStore("auth", () => {
  const loading = ref(false);
  const sessionChecked = ref(false);
  const errorMessage = ref("");
  const user = ref<LoginUser | null>(null);
  const roles = ref<AdminRole[]>([]);
  const permissions = ref<AdminPermission[]>([]);
  const tenantMembers = ref<AdminTenantMember[]>([]);
  const navigation = ref<NavigationItem[]>([]);

  const isAuthenticated = computed(() => user.value !== null);
  const permissionCodes = computed(() => {
    const codes = permissions.value.map((permission) => permission.permission_code);
    for (const member of tenantMembers.value) {
      if (member.status !== "active") {
        continue;
      }
      for (const role of member.roles ?? []) {
        codes.push(...(role.permissions ?? []).map((permission) => permission.permission_code));
      }
    }
    return Array.from(new Set(codes));
  });
  const isSuper = computed(() => user.value?.is_super === true);

  function setSession(payload: MeResponse | LoginResponse): void {
    user.value = payload.user;
    roles.value = payload.roles;
    permissions.value = payload.permissions;
    tenantMembers.value = payload.tenant_members;
    navigation.value = payload.navigation;
  }

  async function login(username: string, password: string): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    try {
      const payload = await loginAdmin(username, password);
      setSession(payload);
      sessionChecked.value = true;
    } catch (error) {
      clearSession();
      errorMessage.value = error instanceof ApiError ? error.message : "登录失败。";
      throw error;
    } finally {
      loading.value = false;
    }
  }

  async function restoreSession(): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    try {
      const payload = await getAdminMe();
      setSession(payload);
    } catch (error) {
      clearSession();
      if (!(error instanceof ApiError) || error.status !== 401) {
        errorMessage.value = error instanceof ApiError ? error.message : "恢复登录态失败。";
      }
    } finally {
      sessionChecked.value = true;
      loading.value = false;
    }
  }

  async function logout(): Promise<void> {
    try {
      await logoutAdmin();
    } finally {
      clearSession();
    }
  }

  async function updateProfile(payload: {
    displayName: string;
    phone: string;
    email: string;
  }): Promise<void> {
    errorMessage.value = "";
    try {
      const nextSession = await updateAdminProfile(payload);
      setSession(nextSession);
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "更新个人信息失败。";
      throw error;
    }
  }

  async function changePassword(payload: {
    currentPassword: string;
    newPassword: string;
  }): Promise<void> {
    errorMessage.value = "";
    try {
      await changeAdminPassword(payload);
      clearSession();
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "修改密码失败。";
      throw error;
    }
  }

  function clearSession(): void {
    user.value = null;
    roles.value = [];
    permissions.value = [];
    tenantMembers.value = [];
    navigation.value = [];
    sessionChecked.value = true;
  }

  function expireSession(): void {
    const hadSession = user.value !== null;
    clearSession();
    if (hadSession) {
      errorMessage.value = "登录信息已失效，请重新登录。";
    }
  }

  return {
    loading,
    sessionChecked,
    errorMessage,
    user,
    roles,
    permissions,
    tenantMembers,
    navigation,
    isAuthenticated,
    permissionCodes,
    isSuper,
    login,
    restoreSession,
    logout,
    updateProfile,
    changePassword,
    clearSession,
    expireSession,
  };
});
