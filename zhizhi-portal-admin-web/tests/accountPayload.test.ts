import assert from "node:assert/strict";
import { test } from "node:test";
import { accountPayload } from "../src/accountPayload.ts";

test("account writes strip plaintext and scope record IDs", () => {
  const payload = accountPayload({ username: "demo", display_name: "Demo", email: "", active: true, password: "test-only-password", scopes: [{ id: "record-id", tenant_id: "tenant", organization_unit_id: "" }] }, "encrypted-test-only");
  assert.equal(Object.hasOwn(payload, "password"), false);
  assert.equal(payload.encrypted_password, "encrypted-test-only");
  assert.deepEqual(payload.scopes, [{ tenant_id: "tenant", organization_unit_id: "" }]);
});
test("profile edits without a reset omit the password field", () => {
  const payload = accountPayload({ display_name: "Demo", email: "", active: true, scopes: [] });
  assert.equal(Object.hasOwn(payload, "encrypted_password"), false);
});
