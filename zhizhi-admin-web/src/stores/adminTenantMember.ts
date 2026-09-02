import { ref } from "vue";
import { defineStore } from "pinia";

import {
  deactivateAdminTenantMember,
  listAssignableAdminRoles,
  replaceAdminTenantMemberAuthorization,
} from "@/api/admin";
import { ApiError } from "@/api/http";
import type { AdminScopeRef } from "@/types/admin";
import type { AdminRole } from "@/types/rbac";

export const useAdminTenantMemberStore = defineStore("adminTenantMember", () => {
  const loading = ref(false);
  const saving = ref(false);
  const errorMessage = ref("");
  const assignableRoleErrorMessage = ref("");
  const assignableRoles = ref<AdminRole[]>([]);

  async function load(_scope?: AdminScopeRef): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    assignableRoleErrorMessage.value = "";

    try {
      assignableRoles.value = await listAssignableAdminRoles();
    } catch (error) {
      assignableRoles.value = [];
      assignableRoleErrorMessage.value =
        error instanceof ApiError ? error.message : "Failed to load assignable roles.";
    } finally {
      loading.value = false;
    }
  }

  async function replaceAuthorization(
    scope: AdminScopeRef,
    payload: {
      principalAdminUserId: string;
      roleIds: string[];
      scopes?: AdminScopeRef[];
      status?: string;
    },
  ): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      await replaceAdminTenantMemberAuthorization({
        tenantId: scope.scope_tenant_id,
        adminUserId: payload.principalAdminUserId,
        roleIds: payload.roleIds,
        scopes: payload.scopes ?? [scope],
        status: payload.status ?? "active",
      });
      await load(scope);
    } catch (error) {
      errorMessage.value =
        error instanceof ApiError ? error.message : "Failed to save admin tenant member.";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function revoke(scope: AdminScopeRef, memberId: string): Promise<void> {
    saving.value = true;
    errorMessage.value = "";
    try {
      await deactivateAdminTenantMember(memberId);
      await load(scope);
    } catch (error) {
      errorMessage.value =
        error instanceof ApiError ? error.message : "Failed to revoke admin role.";
      throw error;
    } finally {
      saving.value = false;
    }
  }

  function reset(): void {
    loading.value = false;
    saving.value = false;
    errorMessage.value = "";
    assignableRoleErrorMessage.value = "";
    assignableRoles.value = [];
  }

  return {
    loading,
    saving,
    errorMessage,
    assignableRoleErrorMessage,
    assignableRoles,
    load,
    replaceAuthorization,
    revoke,
    reset,
  };
});
