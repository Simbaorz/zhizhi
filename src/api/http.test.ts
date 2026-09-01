import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, fetchJson, registerUnauthorizedHandler } from "@/api/http";

describe("fetchJson", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { location: { origin: "https://admin.example.test" } });
    vi.stubGlobal("document", { cookie: "zhizhi_admin_csrf=csrf-token" });
  });

  afterEach(() => {
    registerUnauthorizedHandler(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("serializes query/body and sends Cookie credentials with CSRF", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchJson<{ ok: boolean }>("/api/admin/example", {
        method: "POST",
        query: { page: 2, search: "", enabled: true },
        body: { name: "demo" },
      }),
    ).resolves.toEqual({ ok: true });

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://admin.example.test/api/admin/example?page=2&enabled=true");
    expect(new Headers(options.headers).get("Authorization")).toBeNull();
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("csrf-token");
    expect(options.credentials).toBe("include");
    expect(options.body).toBe(JSON.stringify({ name: "demo" }));
  });

  it("turns API detail responses into ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "invalid request" }), {
          status: 422,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(fetchJson("/api/admin/example")).rejects.toEqual(
      new ApiError(422, "invalid request"),
    );
  });

  it("uses a Chinese message when the login token is invalid", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "token invalid" }), {
          status: 401,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(fetchJson("/api/admin/auth/me")).rejects.toEqual(
      new ApiError(401, "登录信息已失效，请重新登录。"),
    );
  });

  it("notifies the auth handler for protected 401 responses", async () => {
    const handler = vi.fn();
    registerUnauthorizedHandler(handler);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "token invalid" }), {
          status: 401,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(fetchJson("/api/admin/users/tenant-admins")).rejects.toBeInstanceOf(
      ApiError,
    );

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not notify the auth handler while restoring a session", async () => {
    const handler = vi.fn();
    registerUnauthorizedHandler(handler);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "token invalid" }), {
          status: 401,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(fetchJson("/api/admin/auth/me")).rejects.toBeInstanceOf(ApiError);

    expect(handler).not.toHaveBeenCalled();
  });

  it("expires the session when the CSRF cookie no longer matches", async () => {
    const handler = vi.fn();
    registerUnauthorizedHandler(handler);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Invalid CSRF token." }), {
          status: 403,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(
      fetchJson("/api/admin/users", { method: "POST", body: {} }),
    ).rejects.toEqual(new ApiError(403, "登录安全信息已失效，请重新登录。"));

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("keeps ordinary permission failures separate from CSRF failures", async () => {
    const handler = vi.fn();
    registerUnauthorizedHandler(handler);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Permission denied." }), {
          status: 403,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(fetchJson("/api/admin/users")).rejects.toEqual(
      new ApiError(403, "当前账号没有操作权限。"),
    );
    expect(handler).not.toHaveBeenCalled();
  });

  it("uses a concise Chinese message instead of an HTML gateway response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html><head><title>502 Bad Gateway</title></head></html>", {
          status: 502,
          headers: { "content-type": "text/html" },
        }),
      ),
    );

    await expect(
      fetchJson("/api/admin/auth/login", { method: "POST" }),
    ).rejects.toEqual(new ApiError(502, "服务暂时不可用，请稍后重试。"));
  });

  it("uses a Chinese credential message for a rejected login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "invalid credentials" }), {
          status: 401,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(
      fetchJson("/api/admin/auth/login", { method: "POST" }),
    ).rejects.toEqual(new ApiError(401, "用户名或密码错误，请重新输入。"));
  });
});
