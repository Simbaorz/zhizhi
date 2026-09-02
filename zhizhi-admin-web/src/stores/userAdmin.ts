import { ref } from "vue";
import { defineStore } from "pinia";

import {
  createOrBindAdminUser,
  listTenantAdminUsers,
  resetAdminUserPassword,
  updateAdminUser,
} from "@/api/admin";
import { ApiError } from "@/api/http";
import type { AdminScopeRef, ManagedUser, PaginationInfo } from "@/types/admin";

interface UserListFilters {
  search?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}

function emptyPagination(): PaginationInfo {
  return { page: 1, page_size: 20, total: 0 };
}

export const useUserAdminStore = defineStore("userAdmin", () => {
  const loading = ref(false);
  const saving = ref(false);
  const errorMessage = ref("");
  const users = ref<ManagedUser[]>([]);
  const pagination = ref<PaginationInfo>(emptyPagination());

  async function loadTenantAdmins(tenantId: string, filters: UserListFilters = {}): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    try {
      const result = await listTenantAdminUsers(tenantId, filters);
      users.value = result.items;
      pagination.value = result.pagination;
    } catch (error) {
      users.value = [];
      pagination.value = emptyPagination();
      errorMessage.value = error instanceof ApiError ? error.message : "加载管理员账号失败。";
    } finally {
      loading.value = false;
    }
  }

  async function createTenantAdmin(
    scope: AdminScopeRef,
    payload: {
      username: string;
      password?: string;
      displayName: string;
      phone?: string;
      email?: string;
      status: string;
    },
  ): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      await createOrBindAdminUser({ tenantId: scope.scope_tenant_id, ...payload });
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "创建或绑定管理员失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function patchUser(
    userId: string,
    payload: {
      displayName?: string;
      phone?: string;
      email?: string;
      status?: string;
    },
    scope: AdminScopeRef,
  ): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      await updateAdminUser(userId, { ...payload, scope });
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "更新管理员失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function resetPassword(
    userId: string,
    password: string,
    scope: AdminScopeRef,
  ): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      await resetAdminUserPassword(userId, password, scope);
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "重置密码失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  function reset(): void {
    loading.value = false;
    saving.value = false;
    errorMessage.value = "";
    users.value = [];
    pagination.value = emptyPagination();
  }

  return {
    loading,
    saving,
    errorMessage,
    users,
    pagination,
    loadTenantAdmins,
    createTenantAdmin,
    patchUser,
    resetPassword,
    reset,
  };
});
