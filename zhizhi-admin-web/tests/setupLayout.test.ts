import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const setupViewSource = readFileSync("src/views/SetupView.vue", "utf8");

describe("setup page layout", () => {
  it("uses a dedicated setup wizard instead of the login shell", () => {
    assert.match(setupViewSource, /class="setup-page"/);
    assert.match(setupViewSource, /<el-steps/);
    assert.match(setupViewSource, /创建超级管理员/);
    assert.doesNotMatch(setupViewSource, /class="login-shell"/);
  });

  it("keeps the setup action on the shared blue-violet brand token", () => {
    assert.match(setupViewSource, /var\(--accent\)/);
    assert.match(setupViewSource, /var\(--accent-strong\)/);
  });
});
