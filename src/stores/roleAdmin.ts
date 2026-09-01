import { ref } from "vue";
import { defineStore } from "pinia";

import {
  createRole,
  deleteRole,
  listPermissions,
  listRolePermissions,
  listRoles,
  replaceRolePermissions,
  updateRole,
} from "@/api/admin";
import { ApiError } from "@/api/http";
import type { PaginationInfo } from "@/types/admin";
import type { AdminPermission, AdminRole } from "@/types/rbac";

interface RoleListFilters {
  search?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}

function emptyPagination(): PaginationInfo {
  return { page: 1, page_size: 20, total: 0 };
}

export const useRoleAdminStore = defineStore("roleAdmin", () => {
  const loading = ref(false);
  const saving = ref(false);
  const errorMessage = ref("");
  const roles = ref<AdminRole[]>([]);
  const pagination = ref<PaginationInfo>(emptyPagination());
  const permissions = ref<AdminPermission[]>([]);
  const selectedRolePermissions = ref<AdminPermission[]>([]);

  async function loadRoles(filters: RoleListFilters = {}): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    try {
      const result = await listRoles(filters);
      roles.value = result.items;
      pagination.value = result.pagination;
    } catch (error) {
      roles.value = [];
      pagination.value = emptyPagination();
      errorMessage.value = error instanceof ApiError ? error.message : "加载角色失败。";
    } finally {
      loading.value = false;
    }
  }

  async function loadPermissions(): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    try {
      permissions.value = await listPermissions();
    } catch (error) {
      permissions.value = [];
      errorMessage.value = error instanceof ApiError ? error.message : "加载权限点失败。";
    } finally {
      loading.value = false;
    }
  }

  async function createNewRole(payload: {
    roleCode: string;
    roleName: string;
    description: string;
    status: string;
    isDelegable?: boolean;
  }): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      await createRole(payload);
      await loadRoles();
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "创建角色失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function patchRole(
    roleId: string,
    payload: {
      roleName?: string;
      description?: string;
      status?: string;
      isDelegable?: boolean;
    },
  ): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      await updateRole(roleId, payload);
      await loadRoles();
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "更新角色失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function removeRole(roleId: string): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      await deleteRole(roleId);
      await loadRoles();
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "删除角色失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function loadRolePermissionSet(roleId: string): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    try {
      selectedRolePermissions.value = await listRolePermissions(roleId);
    } catch (error) {
      selectedRolePermissions.value = [];
      errorMessage.value = error instanceof ApiError ? error.message : "加载角色权限失败。";
    } finally {
      loading.value = false;
    }
  }

  async function saveRolePermissionSet(roleId: string, permissionIds: string[]): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      await replaceRolePermissions(roleId, permissionIds);
      await loadRolePermissionSet(roleId);
      await loadRoles();
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "更新角色权限失败。";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  return {
    loading,
    saving,
    errorMessage,
    roles,
    pagination,
    permissions,
    selectedRolePermissions,
    loadRoles,
    loadPermissions,
    createNewRole,
    patchRole,
    removeRole,
    loadRolePermissionSet,
    saveRolePermissionSet,
  };
});
