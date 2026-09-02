import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { createDefaultSession, isValidAgentSession, normalizeSession } from "../src/utils/session.ts";

describe("temporary Agent sessions", () => {
  it("creates a fresh editable conversation id", () => {
    const session = createDefaultSession(new Date("2026-08-31T10:11:12.000Z"));
    assert.equal(session.conversation_id, "conversation-20260831101112");
    assert.equal(session.principal_type, "user");
  });

  it("requires trusted caller fields and normalizes whitespace", () => {
    const session = normalizeSession({
      conversation_id: " conversation-1 ",
      tenant_id: " tenant-1 ",
      active_organization_unit_id: " sales-east ",
      principal_id: " user-1 ",
      principal_type: " user ",
    });

    assert.equal(session.conversation_id, "conversation-1");
    assert.equal(session.principal_id, "user-1");
    assert.equal(isValidAgentSession(session), true);
    assert.equal(isValidAgentSession({ ...session, tenant_id: "" }), false);
  });
});
