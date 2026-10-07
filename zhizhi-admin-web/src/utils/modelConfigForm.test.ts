import { describe, expect, it } from "vitest";
import { buildModelConfigs, modelConfigFields } from "./modelConfigForm";

describe("model configuration form", () => {
  it("maps editable defaults to the server configuration contract", () => {
    const form = modelConfigFields();
    form.seed = "0";
    const result = buildModelConfigs(form);
    expect(result.generationConfig).toEqual({ temperature: 0.7, top_p: 1, max_tokens: 4096, presence_penalty: 0, frequency_penalty: 0, seed: 0 });
    expect(result.providerConfig).toEqual({ context_window: 32768 });
  });

  it("round trips stored values and preserves configuration outside the editable fields", () => {
    const generation = { temperature: 0, stream: false, seed: 42 };
    const provider = { context_window: 128000, extra_headers: { "x-route": "test" } };
    const form = modelConfigFields(generation, provider);
    form.seed = "";
    const result = buildModelConfigs(form, generation, provider);
    expect(result.generationConfig.temperature).toBe(0);
    expect(result.generationConfig.stream).toBe(false);
    expect(result.generationConfig).not.toHaveProperty("seed");
    expect(result.providerConfig).toEqual(provider);
  });

  it("rejects invalid or out of range numeric fields instead of silently using defaults", () => {
    for (const [key, value] of [["temperature", "NaN"], ["topP", "2"], ["maxTokens", "1.5"], ["contextWindow", "0"], ["seed", "-1"]] as const) {
      const form = modelConfigFields();
      form[key] = value;
      expect(() => buildModelConfigs(form)).toThrow();
    }
  });

  it("omits cleared optional generation parameters and requires the context window", () => {
    const form = modelConfigFields();
    form.temperature = "";
    expect(buildModelConfigs(form).generationConfig).not.toHaveProperty("temperature");
    form.contextWindow = "";
    expect(() => buildModelConfigs(form)).toThrow("上下文窗口");
  });

  it("keeps omitted parameters omitted when editing an existing configuration", () => {
    expect(buildModelConfigs(modelConfigFields({ stream: true })).generationConfig).toEqual({});
    expect(buildModelConfigs(modelConfigFields({ stream: true }), { stream: true }).generationConfig).toEqual({ stream: true });
  });
});
