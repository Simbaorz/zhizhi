import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { parseSseFrame } from "../src/utils/sse.ts";

describe("parseSseFrame", () => {
  it("parses a Gewu assistant delta with correlation fields", () => {
    const event = parseSseFrame(
      'event: assistant_delta\ndata: {"type":"assistant_delta","message_id":"m1","content":"你好","request_id":"r1","conversation_id":"c1"}',
    );

    assert.equal(event?.event, "assistant_delta");
    assert.equal(event?.data.message_id, "m1");
    assert.equal(event?.data.content, "你好");
  });

  it("supports CRLF frames and ignores invalid JSON", () => {
    assert.equal(parseSseFrame("event: done\r\ndata: {}\r\n")?.event, "done");
    assert.equal(parseSseFrame("event: message\ndata: not-json"), null);
  });
});
