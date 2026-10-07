export interface DataSourceResource {
  id: string;
  source_key: string;
  tag: string;
  display_name: string;
  description: string;
  driver: "mysql" | "postgresql";
  status: "active" | "inactive";
  max_rows: number;
  has_credentials: boolean;
  last_test_status: string;
  host?: string;
  port?: number;
  database?: string;
  username?: string;
  server_id?: string;
  endpoint_url?: string;
  connection_revision?: number;
  revision?: number;
  pool_size?: number;
  pool_timeout_seconds?: number;
  connect_timeout_seconds?: number;
  query_timeout_seconds?: number;
  max_result_bytes?: number;
  allowed_schemas?: string[];
  tls?: boolean;
}

export interface DataSourceWrite {
  revision?: number;
  source_key: string;
  tag: string;
  display_name: string;
  description: string;
  driver: "mysql" | "postgresql";
  status: "active" | "inactive";
  host: string;
  port: number;
  database: string;
  username: string;
  password?: string;
  server_id: string;
  endpoint_url: string;
  pool_size: number;
  pool_timeout_seconds: number;
  connect_timeout_seconds: number;
  query_timeout_seconds: number;
  max_rows: number;
  max_result_bytes: number;
  allowed_schemas: string[];
  tls: boolean;
}

export interface DataSourceScope { tenant_id: string; organization_unit_id: string }
export interface DataSourceBinding extends DataSourceScope {
  sources?: DataSourceResource[];
  id?: string;
  source_ids: string[];
  default_source_id: string;
  status: "active" | "inactive";
}
export interface DataSourcePage {
  items: DataSourceResource[];
  pagination: { page: number; page_size: number; total: number };
}
