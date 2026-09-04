import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const source = readFileSync("src/views/ModelManagementView.vue", "utf-8");

describe("model management layout", () => {
  it("uses a single flat management surface with peer tabs", () => {
    assert.match(source, /class="model-management-toolbar"/);
    assert.match(source, /class="model-management-tabs"/);
    assert.match(source, />\s*模型配置\s*</);
    assert.match(source, />\s*可用模型\s*</);
    assert.match(source, />\s*默认模型\s*</);
    assert.doesNotMatch(source, /resource-hero/);
    assert.doesNotMatch(source, /MODEL GOVERNANCE/);
    assert.doesNotMatch(source, /<AppPanel/);
  });

  it("keeps the existing model assignment workflows intact", () => {
    assert.match(source, /openCreateModel/);
    assert.match(source, /openAvailability/);
    assert.match(source, /openBinding/);
    assert.match(source, /向上回溯到最近的组织层级/);
  });

  it("uses the shared structured drawer", () => {
    assert.match(source, /import FormDrawer from "@\/components\/FormDrawer\.vue"/);
    assert.match(source, /<FormDrawer/);
    assert.match(source, /class="model-drawer-form"/);
    assert.doesNotMatch(source, /<el-drawer/);
  });

  it("only exposes OpenAI and Anthropic protocols", () => {
    assert.match(source, /value="openai" label="OpenAI"/);
    assert.match(source, /value="anthropic" label="Anthropic"/);
    assert.doesNotMatch(source, /unicom/i);
  });
});
