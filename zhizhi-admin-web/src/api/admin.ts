import { fetchBlob, fetchJson } from "@/api/http";
import { encryptAdminPassword } from "@/api/passwordCrypto";
import type { LoginResponse, MeResponse } from "@/types/auth";
import type { BootstrapStatus } from "@/types/bootstrap";
import type {
  AdminPermission,
  AdminRole,
  AdminTenantMember,
  NavigationItem,
} from "@/types/rbac";
import type {
  AdminScopeRef,
  BackgroundJob,
  DataSourceScopeType,
  LLMBindingScopeType,
  GitRepositoryTestResult,
  ManagedDataSourceBinding,
  ManagedDataSourceEntitlement,
  ManagedDataSource,
  ManagedFileEntry,
  ManagedGitEntitlement,
  ManagedGitRepository,
  ManagedLLMBinding,
  ManagedLLMConfig,
  ManagedLLMEntitlement,
  ManagedTextFile,
  ManagedOrganizationUnit,
  ManagedTenant,
  ManagedUser,
  PaginatedList,
  PaginationInfo,
  ScopeCatalogNode,
  SkillDetail,
  WorkspaceSceneAsset,
  WorkspaceSceneGitConfig,
  WorkspaceSkillAsset,
  LLMProvider,
  LLMProtocol,
  LLMTestResult,
} from "@/types/admin";

function scopeQuery(scope: AdminScopeRef): Record<string, string> {
  return {
    scope_type: scope.scope_type,
    scope_tenant_id: scope.scope_tenant_id,
    scope_organization_unit_id: scope.scope_organization_unit_id ?? "",
  };
}

export async function getBootstrapStatus(): Promise<BootstrapStatus> {
  return fetchJson<BootstrapStatus>("/api/admin/bootstrap/status");
}

export async function initializeBootstrap(payload: {
  bootstrapToken: string;
  username: string;
  displayName: string;
  password: string;
}): Promise<BootstrapStatus> {
  const encryptedPassword = await encryptAdminPassword(payload.password);
  return fetchJson<BootstrapStatus>("/api/admin/bootstrap", {
    method: "POST",
    body: {
      bootstrap_token: payload.bootstrapToken,
      username: payload.username,
      display_name: payload.displayName,
      encrypted_password: encryptedPassword,
    },
  });
}

function assetScopeQuery(scope: AdminScopeRef): Record<string, string> {
  return {
    scope_type: "tenant",
    scope_tenant_id: scope.scope_tenant_id,
  };
}

interface OrgListQuery {
  page: number;
  pageSize: number;
  search?: string;
  status?: string;
}

function orgListQuery(query: OrgListQuery): Record<string, string | number> {
  return {
    page: query.page,
    page_size: query.pageSize,
    search: query.search ?? "",
    status: query.status ?? "all",
  };
}

function paginationFallback(total: number, query: OrgListQuery): PaginationInfo {
  return {
    page: query.page,
    page_size: query.pageSize,
    total,
  };
}

export async function loginAdmin(username: string, password: string): Promise<LoginResponse> {
  const encryptedPassword = await encryptAdminPassword(password);
  return fetchJson<LoginResponse>("/api/admin/auth/login", {
    method: "POST",
    body: { username, encrypted_password: encryptedPassword },
  });
}

export async function logoutAdmin(): Promise<void> {
  await fetchJson<{ ok: boolean }>("/api/admin/auth/logout", {
    method: "POST",
  });
}

export async function getAdminMe(): Promise<MeResponse> {
  return fetchJson<MeResponse>("/api/admin/auth/me");
}

export async function updateAdminProfile(payload: {
  displayName: string;
  phone: string;
  email: string;
}): Promise<MeResponse> {
  return fetchJson<MeResponse>("/api/admin/auth/me/profile", {
    method: "PATCH",
    body: {
      display_name: payload.displayName,
      phone: payload.phone,
      email: payload.email,
    },
  });
}

export async function changeAdminPassword(payload: {
  currentPassword: string;
  newPassword: string;
}): Promise<void> {
  const [encryptedCurrentPassword, encryptedNewPassword] = await Promise.all([
    encryptAdminPassword(payload.currentPassword),
    encryptAdminPassword(payload.newPassword),
  ]);
  await fetchJson<{ ok: boolean }>("/api/admin/auth/me/password", {
    method: "POST",
    body: {
      encrypted_current_password: encryptedCurrentPassword,
      encrypted_new_password: encryptedNewPassword,
    },
  });
}

export async function getNavigation(): Promise<NavigationItem[]> {
  const response = await fetchJson<{ items: NavigationItem[] }>("/api/admin/auth/navigation");
  return response.items;
}

export async function getScopeCatalog(): Promise<ScopeCatalogNode[]> {
  const response = await fetchJson<{ scopes: ScopeCatalogNode[] }>("/api/admin/scope-catalog");
  return response.scopes;
}

export async function listOrgTenants(): Promise<ManagedTenant[]> {
  const response = await fetchJson<{ tenants: ManagedTenant[] }>("/api/admin/org/tenants");
  return response.tenants;
}

export async function listOrgTenantPage(
  query: OrgListQuery,
): Promise<PaginatedList<ManagedTenant>> {
  const response = await fetchJson<{
    tenants: ManagedTenant[];
    pagination?: PaginationInfo;
  }>("/api/admin/org/tenants", {
    query: orgListQuery(query),
  });
  return {
    items: response.tenants,
    pagination: response.pagination ?? paginationFallback(response.tenants.length, query),
  };
}

export async function createOrgTenant(payload: {
  tenantCode: string;
  tenantName: string;
  status: string;
}): Promise<ManagedTenant> {
  return fetchJson<ManagedTenant>("/api/admin/org/tenants", {
    method: "POST",
    body: {
      tenant_code: payload.tenantCode,
      tenant_name: payload.tenantName,
      status: payload.status,
    },
  });
}

export async function updateOrgTenant(
  tenantId: string,
  payload: {
    tenantName?: string;
    status?: string;
  },
): Promise<ManagedTenant> {
  return fetchJson<ManagedTenant>(`/api/admin/org/tenants/${encodeURIComponent(tenantId)}`, {
    method: "PATCH",
    body: {
      tenant_name: payload.tenantName,
      status: payload.status,
    },
  });
}

export async function deleteOrgTenant(tenantId: string): Promise<void> {
  await fetchJson<{ ok: boolean }>(`/api/admin/org/tenants/${encodeURIComponent(tenantId)}`, {
    method: "DELETE",
  });
}

export async function listOrganizationUnits(tenantId: string): Promise<ManagedOrganizationUnit[]> {
  const response = await fetchJson<{ organization_units: ManagedOrganizationUnit[] }>(
    `/api/admin/org/tenants/${encodeURIComponent(tenantId)}/organization-units`,
  );
  return response.organization_units;
}

export async function listOrganizationUnitPage(
  tenantId: string,
  query: OrgListQuery,
): Promise<PaginatedList<ManagedOrganizationUnit>> {
  const response = await fetchJson<{
    organization_units: ManagedOrganizationUnit[];
    pagination?: PaginationInfo;
  }>(`/api/admin/org/tenants/${encodeURIComponent(tenantId)}/organization-units`, {
    query: orgListQuery(query),
  });
  return {
    items: response.organization_units,
    pagination:
      response.pagination ?? paginationFallback(response.organization_units.length, query),
  };
}

export async function createOrganizationUnit(payload: {
  tenantId: string;
  parentId?: string | null;
  externalKey: string;
  name: string;
  unitType: string;
  metadata?: Record<string, unknown>;
  status: string;
  sortOrder: number;
}): Promise<ManagedOrganizationUnit> {
  return fetchJson<ManagedOrganizationUnit>(
    `/api/admin/org/tenants/${encodeURIComponent(payload.tenantId)}/organization-units`,
    {
    method: "POST",
    body: {
      parent_id: payload.parentId ?? null,
      external_key: payload.externalKey,
      name: payload.name,
      unit_type: payload.unitType,
      metadata: payload.metadata ?? {},
      status: payload.status,
      sort_order: payload.sortOrder,
    },
    },
  );
}

export async function updateOrganizationUnit(
  organizationUnitId: string,
  payload: {
    parentId?: string | null;
    name?: string;
    unitType?: string;
    metadata?: Record<string, unknown>;
    status?: string;
    sortOrder?: number;
  },
): Promise<ManagedOrganizationUnit> {
  return fetchJson<ManagedOrganizationUnit>(
    `/api/admin/org/organization-units/${encodeURIComponent(organizationUnitId)}`,
    {
    method: "PATCH",
    body: {
      parent_id: payload.parentId,
      name: payload.name,
      unit_type: payload.unitType,
      metadata: payload.metadata,
      status: payload.status,
      sort_order: payload.sortOrder,
    },
    },
  );
}

export async function deleteOrganizationUnit(organizationUnitId: string): Promise<void> {
  await fetchJson<{ ok: boolean }>(
    `/api/admin/org/organization-units/${encodeURIComponent(organizationUnitId)}`,
    {
    method: "DELETE",
    },
  );
}

export async function listAssignableAdminRoles(): Promise<AdminRole[]> {
  const response = await fetchJson<{ roles: AdminRole[] }>(
    "/api/admin/tenant-members/assignable-roles",
  );
  return response.roles;
}

export async function replaceAdminTenantMemberAuthorization(payload: {
  tenantId: string;
  adminUserId: string;
  roleIds: string[];
  scopes: AdminScopeRef[];
  status: string;
}): Promise<AdminTenantMember> {
  return fetchJson<AdminTenantMember>("/api/admin/tenant-members", {
    method: "POST",
    body: {
      tenant_id: payload.tenantId,
      admin_user_id: payload.adminUserId,
      role_ids: payload.roleIds,
      scopes: payload.scopes.map(scopeQuery),
      status: payload.status,
    },
  });
}

export async function deactivateAdminTenantMember(memberId: string): Promise<void> {
  await fetchJson<unknown>(`/api/admin/tenant-members/${memberId}`, {
    method: "DELETE",
  });
}

export interface AdminListFilters {
  search?: string;
  status?: string;
  scopeType?: string;
  organizationUnitId?: string;
  page?: number;
  pageSize?: number;
}

function adminListQuery(filters: AdminListFilters = {}): Record<string, string | number> {
  const query: Record<string, string | number> = {
    search: filters.search ?? "",
    status: filters.status ?? "all",
    page: filters.page ?? 1,
    page_size: filters.pageSize ?? 20,
  };
  if (filters.scopeType && filters.scopeType !== "all") {
    query.scope_type = filters.scopeType;
  }
  if (filters.organizationUnitId) {
    query.organization_unit_id = filters.organizationUnitId;
  }
  return query;
}

function adminPaginationFallback(total: number, filters: AdminListFilters): PaginationInfo {
  return {
    page: filters.page ?? 1,
    page_size: filters.pageSize ?? 20,
    total,
  };
}

export interface LLMModelListFilters extends AdminListFilters {
  provider?: string;
  tenantId?: string;
}

export async function listLLMModels(
  filters: LLMModelListFilters = {},
): Promise<ManagedLLMConfig[]> {
  const result = await listLLMModelPage({
    ...filters,
    page: filters.page ?? 1,
    pageSize: filters.pageSize ?? 100,
  });
  return result.items;
}

export async function listLLMModelPage(
  filters: LLMModelListFilters = {},
): Promise<PaginatedList<ManagedLLMConfig>> {
  const response = await fetchJson<{ models: ManagedLLMConfig[]; pagination?: PaginationInfo }>("/api/admin/llm/models", {
    query: {
      ...adminListQuery(filters),
      provider: filters.provider ?? "all",
      tenant_id: filters.tenantId,
    },
  });
  return {
    items: response.models,
    pagination: response.pagination ?? adminPaginationFallback(response.models.length, filters),
  };
}

export async function createLLMModel(payload: {
  alias: string;
  displayName: string;
  provider: LLMProvider;
  protocol: LLMProtocol;
  modelName: string;
  endpointUrl: string;
  status: string;
  supportStream: boolean;
  supportTools: boolean;
  supportVision: boolean;
  supportThinking: boolean;
  timeoutSeconds: number;
  generationConfig: Record<string, unknown>;
  providerConfig: Record<string, unknown>;
  credentials: Record<string, unknown>;
}): Promise<ManagedLLMConfig> {
  return fetchJson<ManagedLLMConfig>("/api/admin/llm/models", {
    method: "POST",
    body: {
      alias: payload.alias,
      display_name: payload.displayName,
      provider: payload.provider,
      protocol: payload.protocol,
      model_name: payload.modelName,
      endpoint_url: payload.endpointUrl,
      status: payload.status,
      support_stream: payload.supportStream,
      support_tools: payload.supportTools,
      support_vision: payload.supportVision,
      support_thinking: payload.supportThinking,
      timeout_seconds: payload.timeoutSeconds,
      generation_config: payload.generationConfig,
      provider_config: payload.providerConfig,
      credentials: payload.credentials,
    },
  });
}

export async function updateLLMModel(
  modelId: string,
  payload: {
    displayName?: string;
    modelName?: string;
    endpointUrl?: string;
    status?: string;
    supportStream?: boolean;
    supportTools?: boolean;
    supportVision?: boolean;
    supportThinking?: boolean;
    timeoutSeconds?: number;
    generationConfig?: Record<string, unknown>;
    providerConfig?: Record<string, unknown>;
  },
): Promise<ManagedLLMConfig> {
  return fetchJson<ManagedLLMConfig>(`/api/admin/llm/models/${modelId}`, {
    method: "PATCH",
    body: {
      display_name: payload.displayName,
      model_name: payload.modelName,
      endpoint_url: payload.endpointUrl,
      status: payload.status,
      support_stream: payload.supportStream,
      support_tools: payload.supportTools,
      support_vision: payload.supportVision,
      support_thinking: payload.supportThinking,
      timeout_seconds: payload.timeoutSeconds,
      generation_config: payload.generationConfig,
      provider_config: payload.providerConfig,
    },
  });
}

export async function deleteLLMModel(modelId: string): Promise<void> {
  await fetchJson<unknown>(`/api/admin/llm/models/${modelId}`, {
    method: "DELETE",
  });
}

export async function updateLLMCredentials(
  modelId: string,
  credentials: Record<string, unknown>,
): Promise<ManagedLLMConfig> {
  return fetchJson<ManagedLLMConfig>(`/api/admin/llm/models/${modelId}/credentials`, {
    method: "PUT",
    body: { credentials },
  });
}

export async function listLLMBindings(
  tenantId?: string,
  filters: AdminListFilters = {},
): Promise<ManagedLLMBinding[]> {
  const result = await listLLMBindingPage(tenantId, {
    ...filters,
    page: filters.page ?? 1,
    pageSize: filters.pageSize ?? 100,
  });
  return result.items;
}

export async function listLLMBindingPage(
  tenantId?: string,
  filters: AdminListFilters = {},
): Promise<PaginatedList<ManagedLLMBinding>> {
  const response = await fetchJson<{ bindings: ManagedLLMBinding[]; pagination?: PaginationInfo }>("/api/admin/llm/bindings", {
    query: {
      ...(tenantId ? { tenant_id: tenantId } : {}),
      ...adminListQuery(filters),
    },
  });
  return {
    items: response.bindings,
    pagination: response.pagination ?? adminPaginationFallback(response.bindings.length, filters),
  };
}

export async function listLLMEntitlements(
  tenantId?: string,
  filters: AdminListFilters = {},
): Promise<PaginatedList<ManagedLLMEntitlement>> {
  const response = await fetchJson<{ entitlements: ManagedLLMEntitlement[]; pagination?: PaginationInfo }>(
    "/api/admin/llm/entitlements",
    {
      query: {
        ...(tenantId ? { tenant_id: tenantId } : {}),
        ...adminListQuery(filters),
      },
    },
  );
  return {
    items: response.entitlements,
    pagination: response.pagination ?? adminPaginationFallback(response.entitlements.length, filters),
  };
}

export async function createLLMEntitlement(payload: {
  tenantId: string;
  scopeType: LLMBindingScopeType;
  organizationUnitId: string;
  llmConfigId: string;
  status: string;
}): Promise<ManagedLLMEntitlement> {
  return fetchJson<ManagedLLMEntitlement>("/api/admin/llm/entitlements", {
    method: "POST",
    body: {
      tenant_id: payload.tenantId,
      scope_type: payload.scopeType,
      organization_unit_id: payload.organizationUnitId,
      llm_config_id: payload.llmConfigId,
      status: payload.status,
    },
  });
}

export async function createLLMEntitlements(payload: {
  tenantId: string;
  scopeType: LLMBindingScopeType;
  organizationUnitId: string;
  llmConfigIds: string[];
  status: string;
}): Promise<ManagedLLMEntitlement[]> {
  const response = await fetchJson<{ entitlements: ManagedLLMEntitlement[] }>("/api/admin/llm/entitlements/batch", {
    method: "POST",
    body: {
      tenant_id: payload.tenantId,
      scope_type: payload.scopeType,
      organization_unit_id: payload.organizationUnitId,
      llm_config_ids: payload.llmConfigIds,
      status: payload.status,
    },
  });
  return response.entitlements;
}

export async function updateLLMEntitlement(
  entitlementId: string,
  payload: {
    status?: string;
  },
): Promise<ManagedLLMEntitlement> {
  return fetchJson<ManagedLLMEntitlement>(`/api/admin/llm/entitlements/${entitlementId}`, {
    method: "PATCH",
    body: {
      status: payload.status,
    },
  });
}

export async function deleteLLMEntitlement(entitlementId: string): Promise<void> {
  await fetchJson<unknown>(`/api/admin/llm/entitlements/${entitlementId}`, {
    method: "DELETE",
  });
}

export async function createLLMBinding(payload: {
  tenantId: string;
  scopeType: LLMBindingScopeType;
  organizationUnitId: string;
  llmConfigId: string;
  status: string;
  runtimeOverrides: Record<string, unknown>;
}): Promise<ManagedLLMBinding> {
  return fetchJson<ManagedLLMBinding>("/api/admin/llm/bindings", {
    method: "POST",
    body: {
      tenant_id: payload.tenantId,
      scope_type: payload.scopeType,
      organization_unit_id: payload.organizationUnitId,
      llm_config_id: payload.llmConfigId,
      status: payload.status,
      runtime_overrides: payload.runtimeOverrides,
    },
  });
}

export async function updateLLMBinding(
  bindingId: string,
  payload: {
    llmConfigId?: string;
    status?: string;
    runtimeOverrides?: Record<string, unknown>;
  },
): Promise<ManagedLLMBinding> {
  return fetchJson<ManagedLLMBinding>(`/api/admin/llm/bindings/${bindingId}`, {
    method: "PATCH",
    body: {
      llm_config_id: payload.llmConfigId,
      status: payload.status,
      runtime_overrides: payload.runtimeOverrides,
    },
  });
}

export async function deleteLLMBinding(bindingId: string): Promise<void> {
  await fetchJson<unknown>(`/api/admin/llm/bindings/${bindingId}`, {
    method: "DELETE",
  });
}

export async function listDataSources(
  filters: AdminListFilters = {},
): Promise<ManagedDataSource[]> {
  const result = await listDataSourcePage({
    ...filters,
    page: filters.page ?? 1,
    pageSize: filters.pageSize ?? 100,
  });
  return result.items;
}

export async function listDataSourcePage(
  filters: AdminListFilters = {},
): Promise<PaginatedList<ManagedDataSource>> {
  const response = await fetchJson<{ sources: ManagedDataSource[]; pagination?: PaginationInfo }>(
    "/api/admin/data-sources/sources",
    {
      query: adminListQuery(filters),
    },
  );
  return {
    items: response.sources,
    pagination: response.pagination ?? adminPaginationFallback(response.sources.length, filters),
  };
}

export async function createDataSource(payload: {
  sourceKey: string;
  displayName: string;
  description: string;
  status: string;
  apiUrl: string;
  appId: string;
  appKey: string;
  appSecret: string;
  defaultDatabaseKey: string;
  execSourcesCode: string;
  timeoutSeconds: number;
  defaultMaxRows: number;
  hardMaxRows: number;
  allowDatabases: string;
  logSql: boolean;
}): Promise<ManagedDataSource> {
  return fetchJson<ManagedDataSource>("/api/admin/data-sources/sources", {
    method: "POST",
    body: {
      source_key: payload.sourceKey,
      display_name: payload.displayName,
      description: payload.description,
      status: payload.status,
      api_url: payload.apiUrl,
      app_id: payload.appId,
      app_key: payload.appKey,
      app_secret: payload.appSecret,
      default_database_key: payload.defaultDatabaseKey,
      exec_sources_code: payload.execSourcesCode,
      timeout_seconds: payload.timeoutSeconds,
      default_max_rows: payload.defaultMaxRows,
      hard_max_rows: payload.hardMaxRows,
      allow_databases: payload.allowDatabases,
      log_sql: payload.logSql,
    },
  });
}

export async function updateDataSource(
  sourceId: string,
  payload: {
    displayName?: string;
    description?: string;
    status?: string;
    apiUrl?: string;
    appId?: string;
    appKey?: string;
    appSecret?: string;
    defaultDatabaseKey?: string;
    execSourcesCode?: string;
    timeoutSeconds?: number;
    defaultMaxRows?: number;
    hardMaxRows?: number;
    allowDatabases?: string;
    logSql?: boolean;
  },
): Promise<ManagedDataSource> {
  return fetchJson<ManagedDataSource>(`/api/admin/data-sources/sources/${sourceId}`, {
    method: "PATCH",
    body: {
      display_name: payload.displayName,
      description: payload.description,
      status: payload.status,
      api_url: payload.apiUrl,
      app_id: payload.appId,
      app_key: payload.appKey,
      app_secret: payload.appSecret,
      default_database_key: payload.defaultDatabaseKey,
      exec_sources_code: payload.execSourcesCode,
      timeout_seconds: payload.timeoutSeconds,
      default_max_rows: payload.defaultMaxRows,
      hard_max_rows: payload.hardMaxRows,
      allow_databases: payload.allowDatabases,
      log_sql: payload.logSql,
    },
  });
}

export async function deleteDataSource(sourceId: string): Promise<void> {
  await fetchJson<unknown>(`/api/admin/data-sources/sources/${sourceId}`, {
    method: "DELETE",
  });
}

export async function listDataSourceBindings(
  tenantId?: string,
  filters: AdminListFilters = {},
): Promise<ManagedDataSourceBinding[]> {
  const result = await listDataSourceBindingPage(tenantId, {
    ...filters,
    page: filters.page ?? 1,
    pageSize: filters.pageSize ?? 100,
  });
  return result.items;
}

export async function listDataSourceBindingPage(
  tenantId?: string,
  filters: AdminListFilters = {},
): Promise<PaginatedList<ManagedDataSourceBinding>> {
  const response = await fetchJson<{ bindings: ManagedDataSourceBinding[]; pagination?: PaginationInfo }>(
    "/api/admin/data-sources/bindings",
    {
      query: {
        ...(tenantId ? { tenant_id: tenantId } : {}),
        ...adminListQuery(filters),
      },
    },
  );
  return {
    items: response.bindings,
    pagination: response.pagination ?? adminPaginationFallback(response.bindings.length, filters),
  };
}

export async function listDataSourceEntitlements(
  tenantId?: string,
  filters: AdminListFilters = {},
): Promise<PaginatedList<ManagedDataSourceEntitlement>> {
  const response = await fetchJson<{ entitlements: ManagedDataSourceEntitlement[]; pagination?: PaginationInfo }>(
    "/api/admin/data-sources/entitlements",
    {
      query: {
        ...(tenantId ? { tenant_id: tenantId } : {}),
        ...adminListQuery(filters),
      },
    },
  );
  return {
    items: response.entitlements,
    pagination: response.pagination ?? adminPaginationFallback(response.entitlements.length, filters),
  };
}

export async function createDataSourceEntitlement(payload: {
  tenantId: string;
  scopeType: DataSourceScopeType;
  organizationUnitId: string;
  dataSourceIds: string[];
  status: string;
}): Promise<ManagedDataSourceEntitlement[]> {
  const response = await fetchJson<{ entitlements: ManagedDataSourceEntitlement[] }>("/api/admin/data-sources/entitlements", {
    method: "POST",
    body: {
      tenant_id: payload.tenantId,
      scope_type: payload.scopeType,
      organization_unit_id: payload.organizationUnitId,
      data_source_ids: payload.dataSourceIds,
      status: payload.status,
    },
  });
  return response.entitlements;
}

export async function updateDataSourceEntitlement(
  entitlementId: string,
  payload: {
    status?: string;
  },
): Promise<ManagedDataSourceEntitlement> {
  return fetchJson<ManagedDataSourceEntitlement>(
    `/api/admin/data-sources/entitlements/${entitlementId}`,
    {
      method: "PATCH",
      body: {
        status: payload.status,
      },
    },
  );
}

export async function deleteDataSourceEntitlement(entitlementId: string): Promise<void> {
  await fetchJson<unknown>(`/api/admin/data-sources/entitlements/${entitlementId}`, {
    method: "DELETE",
  });
}

export async function createDataSourceBinding(payload: {
  tenantId: string;
  scopeType: DataSourceScopeType;
  organizationUnitId: string;
  dataSourceId: string;
  status: string;
}): Promise<ManagedDataSourceBinding> {
  return fetchJson<ManagedDataSourceBinding>("/api/admin/data-sources/bindings", {
    method: "POST",
    body: {
      tenant_id: payload.tenantId,
      scope_type: payload.scopeType,
      organization_unit_id: payload.organizationUnitId,
      data_source_id: payload.dataSourceId,
      status: payload.status,
    },
  });
}

export async function updateDataSourceBinding(
  bindingId: string,
  payload: {
    status?: string;
  },
): Promise<ManagedDataSourceBinding> {
  return fetchJson<ManagedDataSourceBinding>(
    `/api/admin/data-sources/bindings/${bindingId}`,
    {
      method: "PATCH",
      body: {
        status: payload.status,
      },
    },
  );
}

export async function deleteDataSourceBinding(bindingId: string): Promise<void> {
  await fetchJson<unknown>(`/api/admin/data-sources/bindings/${bindingId}`, {
    method: "DELETE",
  });
}

export async function validateLLMModel(modelId: string): Promise<{ ok: boolean; message: string }> {
  return fetchJson<{ ok: boolean; message: string }>(`/api/admin/llm/models/${modelId}/validate`, {
    method: "POST",
  });
}

export async function testLLMModel(
  modelId: string,
  payload: {
    prompt: string;
    systemPrompt: string;
  },
): Promise<LLMTestResult> {
  return fetchJson<LLMTestResult>(`/api/admin/llm/models/${modelId}/test`, {
    method: "POST",
    body: {
      prompt: payload.prompt,
      system_prompt: payload.systemPrompt,
    },
  });
}

export async function listTenantAdminUsers(
  tenantId: string,
  filters: AdminListFilters = {},
): Promise<PaginatedList<ManagedUser>> {
  const response = await fetchJson<{ users: ManagedUser[]; pagination?: PaginationInfo }>("/api/admin/users/tenant-admins", {
    query: {
      tenant_id: tenantId,
      ...adminListQuery(filters),
    },
  });
  return {
    items: response.users,
    pagination: response.pagination ?? adminPaginationFallback(response.users.length, filters),
  };
}

export async function updateAdminUser(
  userId: string,
  payload: {
    displayName?: string;
    phone?: string;
    email?: string;
    status?: string;
    scope?: AdminScopeRef;
  },
): Promise<ManagedUser> {
  return fetchJson<ManagedUser>(`/api/admin/users/${userId}`, {
      method: "PATCH",
      body: {
        display_name: payload.displayName,
        phone: payload.phone,
        email: payload.email,
        status: payload.status,
        ...(payload.scope ? scopeQuery(payload.scope) : {}),
    },
  });
}

export async function resetAdminUserPassword(
  userId: string,
  password: string,
  scope?: AdminScopeRef,
): Promise<void> {
  const encryptedPassword = await encryptAdminPassword(password);
  await fetchJson<{ ok: boolean }>(`/api/admin/users/${userId}/reset-password`, {
    method: "POST",
    body: {
      encrypted_password: encryptedPassword,
      ...(scope ? scopeQuery(scope) : {}),
    },
  });
}

export async function createOrBindAdminUser(payload: {
  tenantId: string;
  username: string;
  password?: string;
  displayName: string;
  phone?: string;
  email?: string;
  status: string;
}): Promise<AdminTenantMember> {
  const encryptedPassword = payload.password
    ? await encryptAdminPassword(payload.password)
    : "";
  return fetchJson<AdminTenantMember>("/api/admin/users/create-or-bind", {
    method: "POST",
    body: {
      tenant_id: payload.tenantId,
      username: payload.username,
      encrypted_password: encryptedPassword,
      display_name: payload.displayName,
      phone: payload.phone,
      email: payload.email,
      status: payload.status,
    },
  });
}

export async function listRoles(filters: AdminListFilters = {}): Promise<PaginatedList<AdminRole>> {
  const response = await fetchJson<{ roles: AdminRole[]; pagination?: PaginationInfo }>("/api/admin/roles", {
    query: adminListQuery(filters),
  });
  return {
    items: response.roles,
    pagination: response.pagination ?? adminPaginationFallback(response.roles.length, filters),
  };
}

export async function createRole(payload: {
  roleCode: string;
  roleName: string;
  description: string;
  status: string;
  isDelegable?: boolean;
}): Promise<AdminRole> {
  return fetchJson<AdminRole>("/api/admin/roles", {
    method: "POST",
    body: {
      role_code: payload.roleCode,
      role_name: payload.roleName,
      description: payload.description,
      status: payload.status,
      is_delegable: payload.isDelegable,
    },
  });
}

export async function updateRole(
  roleId: string,
  payload: {
    roleName?: string;
    description?: string;
    status?: string;
    isDelegable?: boolean;
  },
): Promise<AdminRole> {
  return fetchJson<AdminRole>(`/api/admin/roles/${roleId}`, {
    method: "PATCH",
    body: {
      role_name: payload.roleName,
      description: payload.description,
      status: payload.status,
      is_delegable: payload.isDelegable,
    },
  });
}

export async function deleteRole(roleId: string): Promise<void> {
  await fetchJson<{ ok: boolean }>(`/api/admin/roles/${roleId}`, {
    method: "DELETE",
  });
}

export async function listPermissions(): Promise<AdminPermission[]> {
  const response = await fetchJson<{ permissions: AdminPermission[] }>("/api/admin/permissions");
  return response.permissions;
}

export async function listRolePermissions(roleId: string): Promise<AdminPermission[]> {
  const response = await fetchJson<{ permissions: AdminPermission[] }>(
    `/api/admin/roles/${roleId}/permissions`,
  );
  return response.permissions;
}

export async function replaceRolePermissions(roleId: string, permissionIds: string[]): Promise<void> {
  await fetchJson<{ ok: boolean }>(`/api/admin/roles/${roleId}/permissions`, {
    method: "PUT",
    body: { permission_ids: permissionIds },
  });
}

export async function listSkillEntries(
  scope: AdminScopeRef,
  path = ".skills",
): Promise<ManagedFileEntry[]> {
  const response = await fetchJson<{ entries: ManagedFileEntry[] }>("/api/admin/skill-files/entries", {
    query: {
      ...assetScopeQuery(scope),
      path,
    },
  });
  return response.entries;
}

export async function readSkillFile(scope: AdminScopeRef, path: string): Promise<ManagedTextFile> {
  return fetchJson<ManagedTextFile>("/api/admin/skill-files/file", {
    query: {
      ...assetScopeQuery(scope),
      path,
    },
  });
}

export async function writeSkillFile(payload: {
  scope: AdminScopeRef;
  path: string;
  content: string;
  expectedVersion?: string | null;
}): Promise<ManagedTextFile> {
  return fetchJson<ManagedTextFile>("/api/admin/skill-files/file", {
    method: "PUT",
    body: {
      ...assetScopeQuery(payload.scope),
      path: payload.path,
      content: payload.content,
      expected_version: payload.expectedVersion ?? null,
    },
  });
}

export async function downloadSkillPath(scope: AdminScopeRef, path: string): Promise<Blob> {
  return fetchBlob("/api/admin/skill-files/download", {
    query: {
      ...assetScopeQuery(scope),
      path,
    },
  });
}

export async function uploadSkillFile(scope: AdminScopeRef, path: string, file: File): Promise<ManagedFileEntry> {
  return fetchJson<ManagedFileEntry>("/api/admin/skill-files/upload", {
    method: "PUT",
    query: {
      ...assetScopeQuery(scope),
      path,
    },
    headers: {
      "Content-Type": file.type || "application/octet-stream",
    },
    body: file,
  });
}

export async function uploadSkillPackage(scope: AdminScopeRef, path: string, file: File): Promise<ManagedFileEntry> {
  return fetchJson<ManagedFileEntry>("/api/admin/skill-files/package", {
    method: "PUT",
    query: {
      ...assetScopeQuery(scope),
      path,
    },
    headers: {
      "Content-Type": file.type || "application/zip",
    },
    body: file,
  });
}

export async function createSkillDirectory(scope: AdminScopeRef, path: string): Promise<void> {
  await fetchJson<{ ok: boolean }>("/api/admin/skill-files/directories", {
    method: "POST",
    body: {
      ...assetScopeQuery(scope),
      path,
    },
  });
}

export async function moveSkillPath(
  scope: AdminScopeRef,
  srcPath: string,
  dstPath: string,
): Promise<void> {
  await fetchJson<{ ok: boolean }>("/api/admin/skill-files/move", {
    method: "POST",
    body: {
      ...assetScopeQuery(scope),
      src_path: srcPath,
      dst_path: dstPath,
    },
  });
}

export async function deleteSkillPath(
  scope: AdminScopeRef,
  path: string,
  recursive: boolean,
): Promise<void> {
  await fetchJson<{ ok: boolean }>("/api/admin/skill-files", {
    method: "DELETE",
    body: {
      ...assetScopeQuery(scope),
      path,
      recursive,
    },
  });
}

export async function listSkills(scope: AdminScopeRef): Promise<WorkspaceSkillAsset[]> {
  const response = await fetchJson<{ assets: WorkspaceSkillAsset[] }>("/api/admin/skills", {
    query: assetScopeQuery(scope),
  });
  return response.assets;
}

export async function getSkill(scope: AdminScopeRef, skillAssetKey: string): Promise<SkillDetail> {
  return fetchJson<SkillDetail>(`/api/admin/skills/${encodeURIComponent(skillAssetKey)}`, {
    query: assetScopeQuery(scope),
  });
}

export async function createSkill(payload: {
  scope: AdminScopeRef;
  name: string;
  description: string;
  status: string;
  content: string;
}): Promise<SkillDetail> {
  return fetchJson<SkillDetail>("/api/admin/skills", {
    method: "POST",
    body: {
      ...assetScopeQuery(payload.scope),
      name: payload.name,
      description: payload.description,
      status: payload.status,
      content: payload.content,
      source: "admin",
    },
  });
}

export async function uploadNewSkillPackage(
  scope: AdminScopeRef,
  name: string,
  file: File,
): Promise<SkillDetail> {
  return fetchJson<SkillDetail>("/api/admin/skills/package", {
    method: "PUT",
    query: {
      ...assetScopeQuery(scope),
      name,
    },
    headers: {
      "Content-Type": file.type || "application/zip",
    },
    body: file,
  });
}

export async function putSkill(
  scope: AdminScopeRef,
  skillAssetKey: string,
  payload: {
    name: string;
    description: string;
    status: string;
    content: string;
  },
): Promise<SkillDetail> {
  return fetchJson<SkillDetail>(`/api/admin/skills/${encodeURIComponent(skillAssetKey)}`, {
    method: "PUT",
    body: {
      ...assetScopeQuery(scope),
      name: payload.name,
      description: payload.description,
      status: payload.status,
      content: payload.content,
      source: "admin",
    },
  });
}

export async function deleteSkill(scope: AdminScopeRef, skillAssetKey: string): Promise<void> {
  await fetchJson<{ ok: boolean }>(`/api/admin/skills/${encodeURIComponent(skillAssetKey)}`, {
    method: "DELETE",
    body: {
      ...assetScopeQuery(scope),
    },
  });
}

export async function replaceSkillPackage(
  scope: AdminScopeRef,
  skillAssetKey: string,
  file: File,
): Promise<SkillDetail> {
  return fetchJson<SkillDetail>(`/api/admin/skills/${encodeURIComponent(skillAssetKey)}/package`, {
    method: "PUT",
    query: assetScopeQuery(scope),
    headers: {
      "Content-Type": file.type || "application/zip",
    },
    body: file,
  });
}

export async function listGitRepositoryPage(
  filters: AdminListFilters = {},
): Promise<PaginatedList<ManagedGitRepository>> {
  const response = await fetchJson<{
    repositories: ManagedGitRepository[];
    pagination?: PaginationInfo;
  }>(
    "/api/admin/git-repositories",
    { query: adminListQuery(filters) },
  );
  return {
    items: response.repositories,
    pagination: response.pagination ?? adminPaginationFallback(response.repositories.length, filters),
  };
}

export async function createGitRepository(payload: {
  alias: string;
  displayName: string;
  repoUrl: string;
  defaultBranch: string;
  username: string;
  password: string;
  status: "active" | "inactive";
}): Promise<ManagedGitRepository> {
  return fetchJson<ManagedGitRepository>("/api/admin/git-repositories", {
    method: "POST",
    body: {
      alias: payload.alias,
      display_name: payload.displayName,
      repo_url: payload.repoUrl,
      default_branch: payload.defaultBranch,
      username: payload.username,
      password: payload.password,
      status: payload.status,
    },
  });
}

export async function updateGitRepository(
  repositoryId: string,
  payload: {
    displayName?: string;
    repoUrl?: string;
    defaultBranch?: string;
    status?: "active" | "inactive";
  },
): Promise<ManagedGitRepository> {
  return fetchJson<ManagedGitRepository>(
    `/api/admin/git-repositories/${encodeURIComponent(repositoryId)}`,
    {
      method: "PATCH",
      body: {
        display_name: payload.displayName,
        repo_url: payload.repoUrl,
        default_branch: payload.defaultBranch,
        status: payload.status,
      },
    },
  );
}

export async function updateGitRepositoryCredentials(
  repositoryId: string,
  payload: { username: string; password: string },
): Promise<ManagedGitRepository> {
  return fetchJson<ManagedGitRepository>(
    `/api/admin/git-repositories/${encodeURIComponent(repositoryId)}/credentials`,
    { method: "PATCH", body: payload },
  );
}

export async function deleteGitRepository(repositoryId: string): Promise<void> {
  await fetchJson(`/api/admin/git-repositories/${encodeURIComponent(repositoryId)}`, {
    method: "DELETE",
  });
}

export async function testGitRepository(
  repositoryId: string,
): Promise<GitRepositoryTestResult> {
  return fetchJson<GitRepositoryTestResult>(
    `/api/admin/git-repositories/${encodeURIComponent(repositoryId)}/test`,
    { method: "POST" },
  );
}

export async function listGitEntitlements(
  tenantId: string,
  filters: AdminListFilters = {},
): Promise<{
  entitlements: ManagedGitEntitlement[];
  repositories: ManagedGitRepository[];
  assignable_repositories: ManagedGitRepository[];
  pagination: PaginationInfo;
}> {
  return fetchJson<{
    entitlements: ManagedGitEntitlement[];
    repositories: ManagedGitRepository[];
    assignable_repositories: ManagedGitRepository[];
    pagination: PaginationInfo;
  }>(
    "/api/admin/git-repositories/entitlements/list",
    { query: { tenant_id: tenantId, ...adminListQuery(filters) } },
  );
}

export async function createGitEntitlements(payload: {
  tenantId: string;
  gitRepositoryIds: string[];
  status: "active" | "inactive";
}): Promise<ManagedGitEntitlement[]> {
  const response = await fetchJson<{ entitlements: ManagedGitEntitlement[] }>(
    "/api/admin/git-repositories/entitlements/batch",
    {
      method: "POST",
      body: {
        tenant_id: payload.tenantId,
        git_repository_ids: payload.gitRepositoryIds,
        status: payload.status,
      },
    },
  );
  return response.entitlements;
}

export async function updateGitEntitlement(
  entitlementId: string,
  status: "active" | "inactive",
): Promise<ManagedGitEntitlement> {
  return fetchJson<ManagedGitEntitlement>(
    `/api/admin/git-repositories/entitlements/${encodeURIComponent(entitlementId)}`,
    { method: "PATCH", body: { status } },
  );
}

export async function deleteGitEntitlement(entitlementId: string): Promise<void> {
  await fetchJson(
    `/api/admin/git-repositories/entitlements/${encodeURIComponent(entitlementId)}`,
    { method: "DELETE" },
  );
}

export async function listAvailableGitRepositories(
  scope: AdminScopeRef,
): Promise<ManagedGitRepository[]> {
  const response = await fetchJson<{ repositories: ManagedGitRepository[] }>(
    "/api/admin/git-repositories/available/list",
    { query: { tenant_id: scope.scope_tenant_id } },
  );
  return response.repositories;
}

export async function listScenes(scope: AdminScopeRef): Promise<WorkspaceSceneAsset[]> {
  const response = await fetchJson<{ scenes: WorkspaceSceneAsset[] }>("/api/admin/scenes", {
    query: assetScopeQuery(scope),
  });
  return response.scenes;
}

export async function createScene(payload: {
  scope: AdminScopeRef;
  name: string;
  description: string;
  status: string;
  requiredSkillAssetKey: string;
}): Promise<WorkspaceSceneAsset> {
  return fetchJson<WorkspaceSceneAsset>("/api/admin/scenes", {
    method: "POST",
    body: {
      ...assetScopeQuery(payload.scope),
      name: payload.name,
      description: payload.description,
      status: payload.status,
      source: "admin",
      required_skill_asset_key: payload.requiredSkillAssetKey,
    },
  });
}

export async function createGitScene(payload: {
  scope: AdminScopeRef;
  name: string;
  description: string;
  status: string;
  requiredSkillAssetKey: string;
  gitRepositoryId: string;
  branch: string;
  ref: string;
  subdir: string;
  autoSyncEnabled: boolean;
  dailySyncTime: string;
  timezone: string;
}): Promise<WorkspaceSceneAsset> {
  return fetchJson<WorkspaceSceneAsset>("/api/admin/scenes/git", {
    method: "POST",
    body: {
      ...assetScopeQuery(payload.scope),
      name: payload.name,
      description: payload.description,
      status: payload.status,
      required_skill_asset_key: payload.requiredSkillAssetKey,
      git_repository_id: payload.gitRepositoryId,
      branch: payload.branch,
      ref: payload.ref,
      subdir: payload.subdir,
      auto_sync_enabled: payload.autoSyncEnabled,
      daily_sync_time: payload.dailySyncTime,
      timezone: payload.timezone,
    },
  });
}

export async function uploadNewScenePackage(
  scope: AdminScopeRef,
  name: string,
  file: File,
): Promise<WorkspaceSceneAsset> {
  return fetchJson<WorkspaceSceneAsset>("/api/admin/scenes/package", {
    method: "PUT",
    query: {
      ...assetScopeQuery(scope),
      name,
    },
    headers: {
      "Content-Type": file.type || "application/zip",
    },
    body: file,
  });
}

export async function updateScene(
  scope: AdminScopeRef,
  sceneAssetKey: string,
  payload: {
    name?: string;
    description?: string;
    status?: string;
    requiredSkillAssetKey?: string;
  },
): Promise<WorkspaceSceneAsset> {
  return fetchJson<WorkspaceSceneAsset>(`/api/admin/scenes/${encodeURIComponent(sceneAssetKey)}`, {
    method: "PATCH",
    body: {
      ...assetScopeQuery(scope),
      name: payload.name,
      description: payload.description,
      status: payload.status,
      required_skill_asset_key: payload.requiredSkillAssetKey,
    },
  });
}

export async function deleteScene(scope: AdminScopeRef, sceneAssetKey: string): Promise<void> {
  await fetchJson<{ ok: boolean }>(`/api/admin/scenes/${encodeURIComponent(sceneAssetKey)}`, {
    method: "DELETE",
    body: {
      ...assetScopeQuery(scope),
    },
  });
}

export async function uploadScenePackage(
  scope: AdminScopeRef,
  sceneAssetKey: string,
  file: File,
): Promise<WorkspaceSceneAsset> {
  return fetchJson<WorkspaceSceneAsset>(
    `/api/admin/scenes/${encodeURIComponent(sceneAssetKey)}/package`,
    {
      method: "PUT",
      query: assetScopeQuery(scope),
      headers: {
        "Content-Type": file.type || "application/zip",
      },
      body: file,
    },
  );
}

export async function listSceneEntries(
  scope: AdminScopeRef,
  sceneAssetKey: string,
  path = "",
): Promise<ManagedFileEntry[]> {
  const response = await fetchJson<{ entries: ManagedFileEntry[] }>("/api/admin/scenes/entries", {
    query: {
      ...assetScopeQuery(scope),
      scene_id: sceneAssetKey,
      path,
    },
  });
  return response.entries;
}

export async function readSceneFile(
  scope: AdminScopeRef,
  sceneAssetKey: string,
  path: string,
): Promise<ManagedTextFile> {
  return fetchJson<ManagedTextFile>("/api/admin/scenes/file", {
    query: {
      ...assetScopeQuery(scope),
      scene_id: sceneAssetKey,
      path,
    },
  });
}

export async function writeSceneFile(payload: {
  scope: AdminScopeRef;
  sceneAssetKey: string;
  path: string;
  content: string;
  expectedVersion?: string | null;
}): Promise<ManagedTextFile> {
  return fetchJson<ManagedTextFile>("/api/admin/scenes/file", {
    method: "PUT",
    body: {
      ...assetScopeQuery(payload.scope),
      scene_id: payload.sceneAssetKey,
      path: payload.path,
      content: payload.content,
      expected_version: payload.expectedVersion ?? null,
    },
  });
}

export async function downloadScenePath(
  scope: AdminScopeRef,
  sceneAssetKey: string,
  path = "",
): Promise<Blob> {
  return fetchBlob("/api/admin/scenes/download", {
    query: {
      ...assetScopeQuery(scope),
      scene_id: sceneAssetKey,
      path,
    },
  });
}

export async function uploadSceneFile(
  scope: AdminScopeRef,
  sceneAssetKey: string,
  path: string,
  file: File,
): Promise<ManagedFileEntry> {
  return fetchJson<ManagedFileEntry>("/api/admin/scenes/upload", {
    method: "PUT",
    query: {
      ...assetScopeQuery(scope),
      scene_id: sceneAssetKey,
      path,
    },
    headers: {
      "Content-Type": file.type || "application/octet-stream",
    },
    body: file,
  });
}

export async function uploadSceneDirectoryPackage(
  scope: AdminScopeRef,
  sceneAssetKey: string,
  path: string,
  file: File,
): Promise<ManagedFileEntry> {
  return fetchJson<ManagedFileEntry>("/api/admin/scenes/directory-package", {
    method: "PUT",
    query: {
      ...assetScopeQuery(scope),
      scene_id: sceneAssetKey,
      path,
    },
    headers: {
      "Content-Type": file.type || "application/zip",
    },
    body: file,
  });
}

export async function createSceneDirectory(
  scope: AdminScopeRef,
  sceneAssetKey: string,
  path: string,
): Promise<void> {
  await fetchJson<{ ok: boolean }>("/api/admin/scenes/directories", {
    method: "POST",
    body: {
      ...assetScopeQuery(scope),
      scene_id: sceneAssetKey,
      path,
    },
  });
}

export async function moveScenePath(
  scope: AdminScopeRef,
  sceneAssetKey: string,
  srcPath: string,
  dstPath: string,
): Promise<void> {
  await fetchJson<{ ok: boolean }>("/api/admin/scenes/move", {
    method: "POST",
    body: {
      ...assetScopeQuery(scope),
      scene_id: sceneAssetKey,
      src_path: srcPath,
      dst_path: dstPath,
    },
  });
}

export async function deleteScenePath(
  scope: AdminScopeRef,
  sceneAssetKey: string,
  path: string,
  recursive: boolean,
): Promise<void> {
  await fetchJson<{ ok: boolean }>("/api/admin/scenes/path", {
    method: "DELETE",
    body: {
      ...assetScopeQuery(scope),
      scene_id: sceneAssetKey,
      path,
      recursive,
    },
  });
}

export async function updateSceneGitConfig(
  scope: AdminScopeRef,
  sceneAssetKey: string,
  payload: {
    gitRepositoryId?: string;
    branch?: string;
    ref?: string;
    subdir?: string;
    autoSyncEnabled?: boolean;
    dailySyncTime?: string;
    timezone?: string;
  },
): Promise<WorkspaceSceneGitConfig> {
  return fetchJson<WorkspaceSceneGitConfig>(`/api/admin/scenes/${encodeURIComponent(sceneAssetKey)}/git`, {
    method: "PATCH",
    body: {
      ...assetScopeQuery(scope),
      git_repository_id: payload.gitRepositoryId,
      branch: payload.branch,
      ref: payload.ref,
      subdir: payload.subdir,
      auto_sync_enabled: payload.autoSyncEnabled,
      daily_sync_time: payload.dailySyncTime,
      timezone: payload.timezone,
    },
  });
}

export async function syncSceneGit(scope: AdminScopeRef, sceneAssetKey: string): Promise<BackgroundJob> {
  const response = await fetchJson<{ job: BackgroundJob }>(
    `/api/admin/scenes/${encodeURIComponent(sceneAssetKey)}/sync`,
    {
      method: "POST",
      body: assetScopeQuery(scope),
    },
  );
  return response.job;
}

export async function getSceneGitSyncJob(jobId: string): Promise<BackgroundJob> {
  const response = await fetchJson<{ job: BackgroundJob }>(
    `/api/admin/scenes/sync-jobs/${encodeURIComponent(jobId)}`,
  );
  return response.job;
}

export async function listSceneGitSyncJobs(
  scope: AdminScopeRef,
  sceneAssetKey: string,
): Promise<BackgroundJob[]> {
  const response = await fetchJson<{ jobs: BackgroundJob[] }>(
    `/api/admin/scenes/${encodeURIComponent(sceneAssetKey)}/sync-jobs`,
    { query: assetScopeQuery(scope) },
  );
  return response.jobs;
}
