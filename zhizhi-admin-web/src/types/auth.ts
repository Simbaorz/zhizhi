import type {
  AdminPermission,
  AdminRole,
  AdminTenantMember,
  NavigationItem,
} from "@/types/rbac";

export interface LoginUser {
  id: string;
  username: string;
  display_name: string;
  phone?: string | null;
  email?: string | null;
  status: string;
  is_super: boolean;
  last_login_time?: string | null;
}

export interface LoginResponse {
  user: LoginUser;
  roles: AdminRole[];
  permissions: AdminPermission[];
  tenant_members: AdminTenantMember[];
  navigation: NavigationItem[];
  is_super?: boolean;
}

export interface MeResponse {
  user: LoginUser;
  roles: AdminRole[];
  permissions: AdminPermission[];
  tenant_members: AdminTenantMember[];
  navigation: NavigationItem[];
  is_super: boolean;
}
