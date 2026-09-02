const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const CSRF_COOKIE_NAME = "zhizhi_admin_csrf";
const CSRF_HEADER_NAME = "X-CSRF-Token";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const PUBLIC_AUTH_PATHS = new Set([
  "/api/admin/auth/login",
  "/api/admin/auth/me",
  "/api/admin/auth/password-key",
  "/api/admin/bootstrap",
  "/api/admin/bootstrap/status",
]);

type UnauthorizedHandler = () => void | Promise<void>;

let unauthorizedHandler: UnauthorizedHandler | null = null;
let handlingUnauthorized = false;

type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  method?: string;
  query?: Record<string, QueryValue>;
  body?: unknown;
  headers?: HeadersInit;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function registerUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

function responseDetail(payload: unknown, status: number): string {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    return String((payload as { detail: unknown }).detail).trim();
  }
  if (typeof payload === "string") {
    return payload.trim();
  }
  return `请求失败 (${status})`;
}

function userFacingErrorMessage(path: string, status: number, payload: unknown): string {
  const detail = responseDetail(payload, status);
  const normalizedDetail = detail.toLowerCase();
  const isLoginRequest = path === "/api/admin/auth/login";
  const mentionsInvalidToken =
    normalizedDetail.includes("token") &&
    ["invalid", "expired", "missing", "malformed"].some((word) =>
      normalizedDetail.includes(word),
    );
  const containsHtml = /<(?:!doctype|html|head|body|title|h1|center)\b/i.test(detail);

  if (status === 401 && isLoginRequest) {
    return "用户名或密码错误，请重新输入。";
  }
  if (isInvalidCsrfResponse(status, payload)) {
    return "登录安全信息已失效，请重新登录。";
  }
  if (status === 401 || mentionsInvalidToken) {
    return "登录信息已失效，请重新登录。";
  }
  if (status === 403) {
    if (path === "/api/admin/bootstrap") {
      return "初始化令牌无效。";
    }
    return "当前账号没有操作权限。";
  }
  if (status >= 500 || containsHtml) {
    return "服务暂时不可用，请稍后重试。";
  }
  return detail;
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = new URL(path, API_BASE_URL || window.location.origin);

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") {
        continue;
      }
      url.searchParams.set(key, String(value));
    }
  }

  return url.toString();
}

function buildHeaders(options: RequestOptions, defaultAccept: string): Headers {
  const headers = new Headers(options.headers);
  headers.set("Accept", defaultAccept);

  if (options.body !== undefined && !(options.body instanceof Blob)) {
    headers.set("Content-Type", "application/json");
  }

  attachCsrfHeader(headers, options.method ?? "GET");

  return headers;
}

export function getCsrfToken(): string {
  if (typeof document === "undefined") {
    return "";
  }
  const prefix = `${CSRF_COOKIE_NAME}=`;
  const cookie = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
}

function attachCsrfHeader(headers: Headers, method: string): void {
  if (SAFE_METHODS.has(method.toUpperCase())) {
    return;
  }
  const token = getCsrfToken();
  if (token) {
    headers.set(CSRF_HEADER_NAME, token);
  }
}

export async function fetchJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = buildHeaders(options, "application/json");

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body:
      options.body === undefined
        ? undefined
        : options.body instanceof Blob
          ? options.body
          : JSON.stringify(options.body),
    credentials: "include",
  });

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? ((await response.json()) as unknown) : await response.text();

  if (!response.ok) {
    await notifySessionFailure(path, response.status, payload);
    throw new ApiError(
      response.status,
      userFacingErrorMessage(path, response.status, payload),
    );
  }

  return payload as T;
}

export async function fetchBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  const headers = buildHeaders(options, "application/octet-stream");

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body:
      options.body === undefined
        ? undefined
        : options.body instanceof Blob
          ? options.body
          : JSON.stringify(options.body),
    credentials: "include",
  });

  if (!response.ok) {
    const isJson = response.headers.get("content-type")?.includes("application/json");
    const payload = isJson ? ((await response.json()) as unknown) : await response.text();
    await notifySessionFailure(path, response.status, payload);
    throw new ApiError(
      response.status,
      userFacingErrorMessage(path, response.status, payload),
    );
  }

  return response.blob();
}

function isInvalidCsrfResponse(status: number, payload: unknown): boolean {
  return status === 403 && responseDetail(payload, status).toLowerCase() === "invalid csrf token.";
}

async function notifySessionFailure(
  path: string,
  status: number,
  payload: unknown,
): Promise<void> {
  const sessionInvalid = status === 401 || isInvalidCsrfResponse(status, payload);
  if (
    !sessionInvalid
    || PUBLIC_AUTH_PATHS.has(path)
    || unauthorizedHandler === null
    || handlingUnauthorized
  ) {
    return;
  }
  handlingUnauthorized = true;
  try {
    await unauthorizedHandler();
  } finally {
    handlingUnauthorized = false;
  }
}
