import type {
  ChatAttachment,
  ChatCapabilities,
  ConversationState,
  AgentSession,
  MessagePage,
  SlashCandidate,
  SlashTarget,
  StreamEvent,
} from "@/types";
import { readSseStream } from "@/utils/sse";
import { encryptPasswords, type PasswordKey } from "@/api/passwordCrypto";

const API_BASE = String(import.meta.env.VITE_ZHIZHI_API_BASE_URL || "").replace(/\/$/, "");
let unauthorizedHandler: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null): void { unauthorizedHandler = handler; }

export interface PortalAccount {
  id: string;
  username: string;
  display_name: string;
  email: string;
}

export interface PortalScope {
  id: string;
  tenant_name: string;
  organization_path: string[];
}

export interface PortalConversation {
  id: string;
  scope_id: string;
  title: string;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = "",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function apiUrl(path: string, query?: Record<string, string | number | undefined>): string {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && String(value).length > 0) {
      url.searchParams.set(key, String(value));
    }
  }
  return API_BASE ? url.toString() : `${url.pathname}${url.search}`;
}

function conversationPath(session: AgentSession): string {
  return `/api/conversations/${encodeURIComponent(session.conversation_id)}`;
}

function csrfToken(): string {
  return decodeURIComponent(document.cookie.match(/(?:^|; )zhizhi_portal_user_csrf=([^;]*)/)?.[1] || "");
}

async function responseError(response: Response, fallback: string): Promise<ApiError> {
  let code = "";
  let detail = "";
  try {
    const payload = (await response.json()) as Record<string, unknown>;
    code = typeof payload.code === "string" ? payload.code : "";
    detail = typeof payload.detail === "string" ? payload.detail : "";
  } catch {
    // Ignore invalid error bodies and use the stable fallback below.
  }
  return new ApiError(detail || fallback, response.status, code);
}

async function fetchJson<T>(
  path: string,
  options: RequestInit & { query?: Record<string, string | number | undefined> } = {},
): Promise<T> {
  const { query, ...init } = options;
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("Accept", "application/json");
  if (init.method && init.method.toUpperCase() !== "GET") {
    headers.set("x-csrf-token", csrfToken());
  }
  const response = await fetch(apiUrl(path, query), { ...init, headers });
  if (response.status === 401) unauthorizedHandler?.();
  if (!response.ok) throw await responseError(response, "请求失败，请稍后重试。");
  return (await response.json()) as T;
}

async function passwordKey(): Promise<PasswordKey> {
  return fetchJson<PasswordKey>("/api/auth/password-key");
}

export async function login(username: string, password: string): Promise<PortalAccount> {
  const [encrypted_password] = await encryptPasswords(await passwordKey(), [password]);
  return fetchJson<PortalAccount>("/api/auth/login", {
    method: "POST", body: JSON.stringify({ username, encrypted_password }),
  });
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<{ ok: boolean }> {
  const [encrypted_current_password, encrypted_new_password] = await encryptPasswords(
    await passwordKey(), [currentPassword, newPassword],
  );
  return fetchJson<{ ok: boolean }>("/api/auth/password", {
    method: "POST", body: JSON.stringify({ encrypted_current_password, encrypted_new_password }),
  });
}

export function currentAccount(): Promise<PortalAccount> {
  return fetchJson<PortalAccount>("/api/auth/me");
}

export function logout(): Promise<{ ok: boolean }> {
  return fetchJson<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
}

export function listScopes(): Promise<PortalScope[]> {
  return fetchJson<PortalScope[]>("/api/scopes");
}

export function listConversations(offset = 0, archived = false): Promise<{ items: PortalConversation[]; has_more: boolean }> {
  return fetchJson<{ items: PortalConversation[]; has_more: boolean }>("/api/conversations", {
    query: { limit: 50, offset, archived: archived ? "true" : undefined },
  });
}

export function createConversation(scopeId: string): Promise<PortalConversation> {
  return fetchJson<PortalConversation>("/api/conversations", {
    method: "POST", body: JSON.stringify({ scope_id: scopeId }),
  });
}

export function getConversation(id: string): Promise<PortalConversation> {
  return fetchJson<PortalConversation>(`/api/conversations/${encodeURIComponent(id)}`);
}

export function updateConversation(id: string, patch: { title?: string; archived?: boolean }): Promise<PortalConversation> {
  return fetchJson<PortalConversation>(`/api/conversations/${encodeURIComponent(id)}`, {
    method: "PATCH", body: JSON.stringify(patch),
  });
}

export function getCapabilities(session: AgentSession): Promise<ChatCapabilities> {
  return fetchJson<ChatCapabilities>(`${conversationPath(session)}/capabilities`);
}

export async function getSlashCandidates(
  session: AgentSession,
): Promise<SlashCandidate[]> {
  const response = await fetchJson<{ items: SlashCandidate[] }>(
    `${conversationPath(session)}/slash-candidates`,
  );
  return response.items;
}

export function getMessages(
  session: AgentSession,
  beforeSequence?: number,
): Promise<MessagePage> {
  return fetchJson<MessagePage>(
    `${conversationPath(session)}/messages`,
    {
      query: {
        limit: 100,
        before_sequence: beforeSequence,
      },
    },
  );
}

export function getConversationState(session: AgentSession): Promise<ConversationState> {
  return fetchJson<ConversationState>(
    `${conversationPath(session)}/pending-ask`,
  );
}

export async function uploadAttachment(
  session: AgentSession,
  requestId: string,
  file: File,
): Promise<ChatAttachment> {
  const form = new FormData();
  form.set("request_id", requestId);
  form.set("file", file);
  return fetchJson<ChatAttachment>(`${conversationPath(session)}/attachments`, {
    method: "POST",
    body: form,
  });
}

export function attachmentUrl(session: AgentSession, attachmentId: string): string {
  return apiUrl(
    `${conversationPath(session)}/attachments/${encodeURIComponent(attachmentId)}`,
  );
}

async function streamRequest(
  path: string,
  body: Record<string, unknown>,
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
      "x-csrf-token": csrfToken(),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (response.status === 401) unauthorizedHandler?.();
  if (!response.ok) throw await responseError(response, "智能体请求失败。");
  await readSseStream(response, onEvent);
}

export function streamChat(payload: {
  session: AgentSession;
  content: string;
  attachmentIds: string[];
  requestId: string;
  slashTarget: SlashTarget | null;
  signal: AbortSignal;
  onEvent: (event: StreamEvent) => void;
}): Promise<void> {
  return streamRequest(
    `${conversationPath(payload.session)}/chat/stream`,
    {
      content: payload.content,
      attachment_ids: payload.attachmentIds,
      request_id: payload.requestId,
      slash_target: payload.slashTarget,
    },
    payload.signal,
    payload.onEvent,
  );
}

export function answerAsk(payload: {
  session: AgentSession;
  askId: string;
  answers: Record<string, string | string[]>;
  status: "answered" | "skipped";
  requestId: string;
  signal: AbortSignal;
  onEvent: (event: StreamEvent) => void;
}): Promise<void> {
  return streamRequest(
    `${conversationPath(payload.session)}/chat/ask-answer`,
    {
      request_id: payload.requestId,
      ask_id: payload.askId,
      status: payload.status,
      answers: payload.answers,
    },
    payload.signal,
    payload.onEvent,
  );
}

export async function interruptConversation(session: AgentSession): Promise<boolean> {
  const response = await fetchJson<{ interrupted: boolean }>(
    `${conversationPath(session)}/chat/interrupt`,
    {
      method: "POST",
    },
  );
  return response.interrupted;
}
