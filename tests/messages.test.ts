import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ChatMessage } from "../src/types.ts";
import { buildDisplayMessages } from "../src/utils/messages.ts";

function message(kind: ChatMessage["kind"], payload: Record<string, unknown>): ChatMessage {
  return {
    message_id: `${kind}-${Math.random()}`,
    conversation_id: "c1",
    role: kind === "tool_result" ? "tool" : "assistant",
    kind,
    content: "",
    payload,
    run_id: "run1",
    request_id: "req1",
  };
}

describe("buildDisplayMessages", () => {
  it("combines matching tool use and result rows", () => {
    const display = buildDisplayMessages([
      message("tool_use", { tool_call_id: "call1", tool_name: "read", arguments: { path: "a" } }),
      message("tool_result", { tool_call_id: "call1", tool_name: "read", result: { ok: true } }),
    ]);

    assert.equal(display.length, 1);
    assert.deepEqual(display[0].payload.tool_result, { ok: true });
  });

  it("keeps ask_user represented by the dedicated ask message", () => {
    const display = buildDisplayMessages([
      message("tool_use", { tool_call_id: "ask1", tool_name: "ask_user" }),
      message("ask", { ask_id: "a1", questions: [{ question: "继续吗？" }] }),
    ]);

    assert.deepEqual(display.map((entry) => entry.kind), ["ask"]);
  });
});
