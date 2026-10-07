import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const source = readFileSync("src/views/ModelManagementView.vue", "utf-8");

describe("model management layout", () => {
  it("uses a single flat management surface with peer tabs", () => {
    assert.match(source, /class="model-management-toolbar(?:\s[^"]*)?"/);
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

  it("uses the shared form surface with modal model editing", () => {
    assert.match(source, /import FormDrawer from "@\/components\/FormDrawer\.vue"/);
    assert.match(source, /<FormDrawer/);
    assert.match(source, /class="model-drawer-form"/);
    assert.match(source, /:placement="drawerMode\?\.startsWith\('model'\) \? 'modal' : 'drawer'"/);
    assert.doesNotMatch(source, /<el-drawer/);
  });

  it("only exposes OpenAI and Anthropic protocols", () => {
    assert.match(source, /value="openai" label="OpenAI Compatible"/);
    assert.match(source, /value="anthropic" label="Anthropic"/);
    assert.doesNotMatch(source, /unicom/i);
  });

  it("exposes connectivity testing and recent results for each model", () => {
    assert.match(source, /@click="openTestModel\(row\)"/);
    assert.match(source, /await testLLMModel\(selectedModel\.value\.id/);
    assert.match(source, /row\.last_test_status/);
    assert.match(source, /row\.last_test_message/);
    assert.match(source, /testResult\.latency_ms/);
    assert.match(source, /testResult\.usage\.total_tokens/);
  });

  it("exposes separate credential editing without reading existing secrets", () => {
    assert.match(source, /@click="openModelCredentials\(row\)"/);
    assert.match(source, /await updateLLMCredentials\(selectedModel\.value\.id/);
    assert.match(source, /:submit-disabled="drawerMode === 'model-credentials' && !credentialsDirty"/);
    assert.match(source, /type="password" autocomplete="new-password"/);
  });
});
