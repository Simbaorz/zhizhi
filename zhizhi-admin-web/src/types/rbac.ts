import type { AdminScopeRef } from "@/types/admin";

export interface AdminRole {
  id: string;
  role_code: string;
  role_name: string;
  description: string;
  status: string;
  is_delegable?: boolean;
  permission_count?: number;
  created_at?: string;
  updated_at?: string;
}

export interface AdminPermission {
  id: string;
  permission_code: string;
  permission_name: string;
  module: string;
  description: string;
  status: string;
}

export interface NavigationItem {
  key: string;
  label: string;
  path: string;
  permission_code: string;
  permission_codes?: string[];
  super_only?: boolean;
}

export interface AdminTenantRole {
  id: string;
  tenant_member_id?: string;
  role_id: string;
  role_code?: string;
  role_name?: string;
  role?: AdminRole | null;
  permissions?: AdminPermission[];
  created_at?: string;
  updated_at?: string;
}

export interface AdminTenantScope {
  id?: string;
  tenant_member_id?: string;
  scope?: AdminScopeRef;
  scope_type?: AdminScopeRef["scope_type"];
  scope_tenant_id?: string;
  scope_organization_unit_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface AdminTenantMember {
  id: string;
  admin_user_id: string;
  tenant_id: string;
  status: "active" | "inactive" | string;
  scope_mode: string;
  roles: AdminTenantRole[];
  scopes: AdminTenantScope[];
  created_by_admin_user_id?: string | null;
  updated_by_admin_user_id?: string | null;
  created_at?: string;
  updated_at?: string;
}
