import type { AccountInput } from "./api";

export function accountPayload(input: AccountInput, encryptedPassword?: string) {
  return {
    username: input.username,
    display_name: input.display_name,
    email: input.email,
    active: input.active,
    scopes: input.scopes.map(({ tenant_id, organization_unit_id }) => ({ tenant_id, organization_unit_id })),
    ...(encryptedPassword ? { encrypted_password: encryptedPassword } : {}),
  };
}
