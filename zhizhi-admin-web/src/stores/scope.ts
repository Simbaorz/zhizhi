import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { getScopeCatalog } from "@/api/admin";
import { ApiError } from "@/api/http";
import type { AdminScopeRef, ScopeCatalogNode, ScopeTreeNode } from "@/types/admin";
import { buildScopeTree, scopeKey } from "@/utils/scope";

const CURRENT_TENANT_STORAGE_KEY = "zhizhi-admin.current-tenant";

export const useScopeStore = defineStore("scope", () => {
  const loading = ref(false);
  const errorMessage = ref("");
  const nodes = ref<ScopeCatalogNode[]>([]);
  const selectedScope = ref<AdminScopeRef | null>(null);
  const selectedAssetTenantScope = ref<AdminScopeRef | null>(null);
  const currentTenantScope = ref<AdminScopeRef | null>(null);
  const expandedKeys = ref<string[]>([]);

  const tree = computed<ScopeTreeNode[]>(() => buildScopeTree(nodes.value));
  const tenantScopes = computed<AdminScopeRef[]>(() => {
    const scopes = new Map<string, AdminScopeRef>();
    for (const node of nodes.value) {
      const tenantId = node.scope.scope_tenant_id;
      if (!tenantId) continue;
      if (node.scope.scope_type === "tenant") {
        scopes.set(tenantId, tenantScope(tenantId));
      } else if (!scopes.has(tenantId)) {
        scopes.set(tenantId, tenantScope(tenantId));
      }
    }
    return Array.from(scopes.values()).sort((left, right) =>
      left.scope_tenant_id.localeCompare(right.scope_tenant_id),
    );
  });
  const currentTenantOptions = computed(() => tenantScopes.value);
  const currentTenantId = computed(() => currentTenantScope.value?.scope_tenant_id ?? "");

  async function fetchCatalog(): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    try {
      nodes.value = await getScopeCatalog();
      reconcileCurrentTenant();
      const tenantId = currentTenantScope.value?.scope_tenant_id ?? "";
      if (!selectedScope.value || selectedScope.value.scope_tenant_id !== tenantId) {
        selectedScope.value = firstSelectableScopeForTenant(tenantId);
      }
      if (!selectedAssetTenantScope.value || selectedAssetTenantScope.value.scope_tenant_id !== tenantId) {
        selectedAssetTenantScope.value = currentTenantScope.value;
      }
      if (selectedScope.value) ensureExpandedParents(selectedScope.value);
    } catch (error) {
      reset();
      errorMessage.value = error instanceof ApiError ? error.message : "加载组织作用域失败。";
    } finally {
      loading.value = false;
    }
  }

  function setSelectedScope(scope: AdminScopeRef | null): void {
    selectedScope.value = scope;
    if (scope) ensureExpandedParents(scope);
  }

  function setSelectedAssetTenantScope(scope: AdminScopeRef | null): void {
    setCurrentTenantScope(scope ? tenantScope(scope.scope_tenant_id) : null);
  }

  function setCurrentTenantScope(scope: AdminScopeRef | null): void {
    const next = scope
      ? currentTenantOptions.value.find(
          (item) => item.scope_tenant_id === scope.scope_tenant_id,
        ) ?? null
      : null;
    currentTenantScope.value = next;
    writeCurrentTenantId(next?.scope_tenant_id ?? "");
    selectedAssetTenantScope.value = next;
    selectedScope.value = next ? firstSelectableScopeForTenant(next.scope_tenant_id) : null;
  }

  function toggleExpanded(key: string): void {
    expandedKeys.value = expandedKeys.value.includes(key)
      ? expandedKeys.value.filter((item) => item !== key)
      : [...expandedKeys.value, key];
  }

  function ensureExpandedParents(scope: AdminScopeRef): void {
    const keys = new Set(expandedKeys.value);
    keys.add(`tenant::${scope.scope_tenant_id}`);
    for (const unit of scope.scope_organization_path ?? []) {
      const matching = nodes.value.find(
        (node) =>
          node.scope.scope_type === "organization_unit"
          && node.scope.scope_organization_unit_id === unit.id,
      );
      if (matching) keys.add(scopeKey(matching.scope));
    }
    keys.add(scopeKey(scope));
    expandedKeys.value = Array.from(keys);
  }

  function reset(): void {
    loading.value = false;
    nodes.value = [];
    selectedScope.value = null;
    selectedAssetTenantScope.value = null;
    currentTenantScope.value = null;
    expandedKeys.value = [];
  }

  function reconcileCurrentTenant(): void {
    const options = currentTenantOptions.value;
    if (options.length === 0) {
      currentTenantScope.value = null;
      writeCurrentTenantId("");
      return;
    }
    const tenantId = currentTenantScope.value?.scope_tenant_id || readCurrentTenantId();
    currentTenantScope.value =
      options.find((scope) => scope.scope_tenant_id === tenantId) ?? options[0] ?? null;
    writeCurrentTenantId(currentTenantScope.value?.scope_tenant_id ?? "");
  }

  function firstSelectableScopeForTenant(tenantId: string): AdminScopeRef | null {
    const scopes = nodes.value
      .filter((node) => node.scope.scope_tenant_id === tenantId)
      .map((node) => node.scope);
    return scopes.find((scope) => scope.scope_type === "tenant") ?? scopes[0] ?? null;
  }

  return {
    loading,
    errorMessage,
    nodes,
    tree,
    tenantScopes,
    currentTenantOptions,
    currentTenantId,
    selectedScope,
    selectedAssetTenantScope,
    currentTenantScope,
    expandedKeys,
    fetchCatalog,
    setSelectedScope,
    setSelectedAssetTenantScope,
    setCurrentTenantScope,
    toggleExpanded,
    reset,
  };
});

function tenantScope(tenantId: string): AdminScopeRef {
  return {
    scope_type: "tenant",
    scope_tenant_id: tenantId,
    scope_organization_unit_id: "",
  };
}

function readCurrentTenantId(): string {
  try {
    return localStorage.getItem(CURRENT_TENANT_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeCurrentTenantId(tenantId: string): void {
  try {
    if (tenantId) localStorage.setItem(CURRENT_TENANT_STORAGE_KEY, tenantId);
    else localStorage.removeItem(CURRENT_TENANT_STORAGE_KEY);
  } catch {
    // The in-memory selection remains usable when browser storage is unavailable.
  }
}
