export type AdminScopeType = "tenant" | "organization_unit";

export interface OrganizationUnitRef {
  id: string;
  external_key: string;
  name: string;
  unit_type: string;
}

export interface AdminScopeRef {
  scope_type: AdminScopeType;
  scope_tenant_id: string;
  scope_organization_unit_id: string;
  scope_organization_path?: OrganizationUnitRef[];
}

export interface ScopeCatalogNode {
  scope: AdminScopeRef;
  label: string;
  tenant_code?: string;
  tenant_name?: string;
  organization_unit_id?: string;
  parent_organization_unit_id?: string;
  external_key?: string;
  unit_type?: string;
}

export interface ScopeTreeNode {
  key: string;
  label: string;
  type: AdminScopeType | "group";
  scope?: AdminScopeRef;
  children: ScopeTreeNode[];
}

export interface PaginationInfo {
  page: number;
  page_size: number;
  total: number;
}

export interface PaginatedList<T> {
  items: T[];
  pagination: PaginationInfo;
}

export interface ManagedUser {
  id: string;
  username: string;
  display_name: string;
  phone?: string | null;
  email?: string | null;
  status: string;
  is_super: boolean;
  created_tenant_id?: string | null;
  created_source?: string;
  created_by_admin_user_id?: string | null;
  updated_by_admin_user_id?: string | null;
  last_login_time?: string | null;
  tenant_member_id?: string;
  role_count?: number;
  tenant_id?: string;
  tenant_admin_status?: string;
  scope_mode?: string;
  roles?: Array<{
    id: string;
    role_id?: string;
    role_code: string;
    role_name: string;
  }>;
  scopes?: Array<{
    scope_id?: string;
    scope_type: AdminScopeType;
    scope_tenant_id: string;
    scope_organization_unit_id: string;
    status: string;
  }>;
}

export interface ManagedTenant {
  id: string;
  tenant_code: string;
  tenant_name: string;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ManagedOrganizationUnit {
  id: string;
  tenant_id: string;
  parent_id?: string | null;
  external_key: string;
  name: string;
  unit_type: string;
  metadata: Record<string, unknown>;
  status: string;
  sort_order: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ManagedFileEntry {
  entry_type: "file" | "directory";
  name: string;
  path: string;
  size_bytes: number;
  version: string;
  modified_at?: string | null;
}

export interface ManagedTextFile {
  path: string;
  content: string;
  version: string;
  modified_at?: string | null;
}

export interface WorkspaceSkillAsset {
  id: string;
  asset_key: string;
  name: string;
  description: string;
  status: string;
  scope_type: string;
  owner_user_id: string | null;
  path: string;
  source: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SkillDetail extends WorkspaceSkillAsset {
  skill_name: string;
  main_file_path: string;
  content: string;
  version: string;
  layout?: "directory" | "flat";
}

export interface WorkspaceSceneGitConfig {
  scene_asset_key: string;
  git_repository_id: string;
  branch: string;
  ref: string;
  subdir: string;
  auto_sync_enabled: boolean;
  daily_sync_time: string;
  timezone: string;
  next_sync_at?: string | null;
  last_synced_at?: string | null;
  last_commit_sha: string;
  last_sync_status: string;
  last_sync_error: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ManagedGitRepository {
  id: string;
  alias: string;
  display_name: string;
  repo_url: string;
  default_branch: string;
  username: string;
  credential_status: string;
  has_credential: boolean;
  status: "active" | "inactive" | string;
  last_test_status: string;
  last_test_message: string;
  last_test_time?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ManagedGitEntitlement {
  id: string;
  tenant_id: string;
  scope_type: "tenant";
  organization_unit_id: string;
  git_repository_id: string;
  status: "active" | "inactive" | string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface GitRepositoryTestResult {
  ok: boolean;
  message: string;
  repository: ManagedGitRepository;
}

export interface BackgroundJob {
  id: string;
  job_id: string;
  job_type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled" | string;
  trigger_type: string;
  target_type: string;
  target_id: string;
  progress: number;
  message: string;
  error: string;
  celery_task_id: string;
  created_by_actor_type: "admin_user" | "system";
  created_by_actor_id: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkspaceSceneAsset {
  id: string;
  asset_key: string;
  name: string;
  description: string;
  path: string;
  mode?: string;
  status: string;
  source: string;
  readonly?: boolean;
  scope_type: string;
  owner_user_id: string | null;
  required_skill_asset_key: string;
  recommended_skill_asset_keys?: string[];
  git?: WorkspaceSceneGitConfig | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export type LLMProvider = "openai" | "anthropic";
export type LLMProtocol = "openai-chat" | "anthropic-messages";

export interface ManagedLLMConfig {
  id: string;
  alias: string;
  display_name: string;
  provider: LLMProvider;
  protocol: LLMProtocol;
  model_name: string;
  endpoint_url: string;
  status: string;
  support_stream: boolean;
  support_tools: boolean;
  support_vision: boolean;
  support_thinking: boolean;
  timeout_seconds: number;
  generation_config: Record<string, unknown>;
  provider_config: Record<string, unknown>;
  credential_status: string;
  has_credentials: boolean;
  credential_fields?: string[];
  last_test_status: "untested" | "success" | "failed" | string;
  last_test_message: string;
  last_test_time?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export type LLMBindingScopeType = "tenant" | "organization_unit";

export interface ManagedLLMBinding {
  id: string;
  tenant_id: string;
  scope_type: LLMBindingScopeType;
  organization_unit_id: string;
  llm_config_id: string;
  status: string;
  runtime_overrides: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ManagedLLMEntitlement {
  id: string;
  tenant_id: string;
  scope_type: LLMBindingScopeType;
  organization_unit_id: string;
  llm_config_id: string;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export type DataSourceScopeType = "tenant" | "organization_unit";

export interface ManagedDataSource {
  id: string;
  source_key: string;
  display_name: string;
  description: string;
  status: string;
  api_url: string;
  app_id: string;
  credential_status: string;
  has_credentials: boolean;
  credential_fields: string[];
  default_database_key: string;
  exec_sources_code: string;
  timeout_seconds: number;
  default_max_rows: number;
  hard_max_rows: number;
  allow_databases: string;
  log_sql: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ManagedDataSourceBinding {
  id: string;
  tenant_id: string;
  scope_type: DataSourceScopeType;
  organization_unit_id: string;
  data_source_id: string;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ManagedDataSourceEntitlement {
  id: string;
  tenant_id: string;
  scope_type: DataSourceScopeType;
  organization_unit_id: string;
  data_source_id: string;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface LLMTestResult {
  ok: boolean;
  content: string;
  latency_ms: number;
  usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  } | null;
  error: string;
}
