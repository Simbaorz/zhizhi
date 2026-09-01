import { computed } from "vue";
import { defineStore } from "pinia";

import { useAuthStore } from "@/stores/auth";
import type { AdminScopeRef } from "@/types/admin";

function tenantMemberScopeToRef(scope: {
  scope?: AdminScopeRef;
  scope_type?: AdminScopeRef["scope_type"];
  scope_tenant_id?: string;
  scope_organization_unit_id?: string;
}): AdminScopeRef | null {
  if (scope.scope) {
    return scope.scope;
  }
  if (!scope.scope_type || !scope.scope_tenant_id) {
    return null;
  }
  return {
    scope_type: scope.scope_type,
    scope_tenant_id: scope.scope_tenant_id,
    scope_organization_unit_id: scope.scope_organization_unit_id ?? "",
  };
}

export const useAdminSessionStore = defineStore("adminSession", () => {
  const authStore = useAuthStore();

  const loading = computed(() => authStore.loading);
  const errorMessage = computed(() => authStore.errorMessage);
  const me = computed(() => authStore.user);
  const tenantMembers = computed(() => authStore.tenantMembers);
  const isSuper = computed(() => authStore.user?.is_super ?? false);

  function reset(): void {
    return;
  }

  async function fetchMe(): Promise<void> {
    await authStore.restoreSession();
  }

  const manageableScopes = computed(() => authStore.tenantMembers
    .flatMap((member) => member.scopes ?? [])
    .map(tenantMemberScopeToRef)
    .filter((scope): scope is AdminScopeRef => scope !== null));

  return {
    loading,
    errorMessage,
    me,
    tenantMembers,
    isSuper,
    manageableScopes,
    reset,
    fetchMe,
  };
});
