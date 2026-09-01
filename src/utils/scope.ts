import type { AdminScopeRef, AdminScopeType, ScopeCatalogNode, ScopeTreeNode } from "@/types/admin";

const TYPE_TEXT: Record<AdminScopeType, string> = {
  tenant: "租户",
  organization_unit: "组织单元",
};

export function scopeKey(scope: AdminScopeRef): string {
  return [
    scope.scope_type,
    scope.scope_tenant_id,
    scope.scope_organization_unit_id ?? "",
  ].join("::");
}

export function scopeTypeText(scopeType: AdminScopeType): string {
  return TYPE_TEXT[scopeType];
}

export function scopeDisplayLabel(scope: AdminScopeRef, explicitLabel?: string): string {
  if (explicitLabel && explicitLabel !== scope.scope_type) {
    return explicitLabel;
  }
  if (scope.scope_type === "tenant") {
    return scope.scope_tenant_id || TYPE_TEXT.tenant;
  }
  const leaf = scope.scope_organization_path?.at(-1);
  return leaf?.name || leaf?.external_key || scope.scope_organization_unit_id || TYPE_TEXT.organization_unit;
}

export function tenantScopeDisplayLabel(scope: AdminScopeRef, nodes: ScopeCatalogNode[]): string {
  const tenantNode = nodes.find(
    (node) =>
      node.scope.scope_type === "tenant"
      && node.scope.scope_tenant_id === scope.scope_tenant_id,
  );
  return tenantNode?.tenant_name?.trim() || tenantNode?.label || scope.scope_tenant_id;
}

export function scopeBreadcrumb(
  scope: AdminScopeRef | null,
  nodes: ScopeCatalogNode[] = [],
): string[] {
  if (!scope) return [];
  return [
    tenantScopeDisplayLabel(scope, nodes),
    ...(scope.scope_organization_path ?? []).map(
      (unit) => unit.name || unit.external_key,
    ),
  ].filter(Boolean);
}

function emptyTenantScope(tenantId: string): AdminScopeRef {
  return {
    scope_type: "tenant",
    scope_tenant_id: tenantId,
    scope_organization_unit_id: "",
  };
}

export function buildScopeTree(nodes: ScopeCatalogNode[]): ScopeTreeNode[] {
  const tenantNodes = new Map<string, ScopeTreeNode>();
  const organizationNodes = new Map<string, ScopeTreeNode>();
  const organizationCatalog = nodes.filter(
    (node) => node.scope.scope_type === "organization_unit",
  );

  for (const node of nodes) {
    const tenantId = node.scope.scope_tenant_id;
    if (!tenantNodes.has(tenantId)) {
      tenantNodes.set(tenantId, {
        key: `tenant::${tenantId}`,
        label: node.tenant_name || node.tenant_code || tenantId,
        type: "tenant",
        scope: emptyTenantScope(tenantId),
        children: [],
      });
    }
    if (node.scope.scope_type === "tenant") {
      const tenant = tenantNodes.get(tenantId)!;
      tenant.label = node.tenant_name || node.label || node.tenant_code || tenantId;
      tenant.scope = node.scope;
    }
  }

  for (const node of organizationCatalog) {
    organizationNodes.set(node.scope.scope_organization_unit_id, {
      key: scopeKey(node.scope),
      label: node.label || node.external_key || node.scope.scope_organization_unit_id,
      type: "organization_unit",
      scope: node.scope,
      children: [],
    });
  }

  for (const node of organizationCatalog) {
    const treeNode = organizationNodes.get(node.scope.scope_organization_unit_id);
    if (!treeNode) continue;
    const parent = organizationNodes.get(node.parent_organization_unit_id ?? "");
    if (parent) {
      parent.children.push(treeNode);
    } else {
      tenantNodes.get(node.scope.scope_tenant_id)?.children.push(treeNode);
    }
  }

  const sortTree = (items: ScopeTreeNode[]): void => {
    items.sort((left, right) => left.label.localeCompare(right.label, "zh-CN"));
    for (const item of items) sortTree(item.children);
  };
  const result = Array.from(tenantNodes.values());
  sortTree(result);
  return result;
}
