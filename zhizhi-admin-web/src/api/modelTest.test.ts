import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { testLLMModel, updateLLMCredentials } from "./admin";

describe("model test and credentials API", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { location: { origin: "https://admin.example.test" } });
    vi.stubGlobal("document", { cookie: "zhizhi_admin_csrf=test-csrf" });
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("submits prompts using the stored model and preserves response and token usage", async () => {
    const result = { ok: true, content: "你好", latency_ms: 250, usage: { input_tokens: 10, output_tokens: 2, total_tokens: 12 }, error: "" };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(testLLMModel("model-1", { prompt: "你好", systemPrompt: "测试助手" })).resolves.toEqual(result);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://admin.example.test/api/admin/llm/models/model-1/test");
    expect(options.method).toBe("POST");
    expect(JSON.parse(String(options.body))).toEqual({ prompt: "你好", system_prompt: "测试助手" });
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("test-csrf");
  });

  it("returns model failure details separately from API errors", async () => {
    const result = { ok: false, content: "", latency_ms: 100, usage: null, error: "模型服务连接超时。" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { headers: { "content-type": "application/json" } })));
    await expect(testLLMModel("model-1", { prompt: "你好", systemPrompt: "" })).resolves.toEqual(result);
  });

  it("reports invalid configurations as API errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "只有 active 模型可以测试。" }), { status: 400, headers: { "content-type": "application/json" } })));
    await expect(testLLMModel("model-1", { prompt: "你好", systemPrompt: "" })).rejects.toThrow("只有 active 模型可以测试。");
  });

  it("updates only the new credential through the dedicated endpoint", async () => {
    const result = { id: "model-1", credential_fields: ["api_key"], has_credentials: true };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(updateLLMCredentials("model-1", { api_key: "fixture-key-not-valid" })).resolves.toEqual(result);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://admin.example.test/api/admin/llm/models/model-1/credentials");
    expect(options.method).toBe("PUT");
    expect(JSON.parse(String(options.body))).toEqual({ credentials: { api_key: "fixture-key-not-valid" } });
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("test-csrf");
  });

  it("surfaces credential validation errors to allow correction", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "API Key 不能为空。" }), { status: 400, headers: { "content-type": "application/json" } })));
    await expect(updateLLMCredentials("model-1", { api_key: "" })).rejects.toThrow("API Key 不能为空。");
  });
});
