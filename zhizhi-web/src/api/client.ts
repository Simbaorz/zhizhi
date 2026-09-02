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

const API_BASE = String(import.meta.env.VITE_ZHIZHI_API_BASE_URL || "").replace(/\/$/, "");

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

function contextQuery(session: AgentSession): Record<string, string> {
  return {
    tenant_id: session.tenant_id,
    active_organization_unit_id: session.active_organization_unit_id,
    principal_id: session.principal_id,
    principal_type: session.principal_type,
  };
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
  const response = await fetch(apiUrl(path, query), { ...init, headers });
  if (!response.ok) throw await responseError(response, "请求失败，请稍后重试。");
  return (await response.json()) as T;
}

export function getCapabilities(session: AgentSession): Promise<ChatCapabilities> {
  return fetchJson<ChatCapabilities>("/api/agent/capabilities", {
    query: contextQuery(session),
  });
}

async function getCatalog(
  session: AgentSession,
  kind: "skills" | "scenes",
): Promise<SlashCandidate[]> {
  const response = await fetchJson<{ items: SlashCandidate[] }>(
    `/api/agent/${kind}`,
    { query: contextQuery(session) },
  );
  return response.items;
}

export function getSkills(session: AgentSession): Promise<SlashCandidate[]> {
  return getCatalog(session, "skills");
}

export function getScenes(session: AgentSession): Promise<SlashCandidate[]> {
  return getCatalog(session, "scenes");
}

export function getMessages(
  session: AgentSession,
  beforeSequence?: number,
): Promise<MessagePage> {
  return fetchJson<MessagePage>(
    `/api/agent/conversations/${encodeURIComponent(session.conversation_id)}/messages`,
    {
      query: {
        ...contextQuery(session),
        limit: 100,
        before_sequence: beforeSequence,
      },
    },
  );
}

export function getConversationState(session: AgentSession): Promise<ConversationState> {
  return fetchJson<ConversationState>(
    `/api/agent/conversations/${encodeURIComponent(session.conversation_id)}/pending-ask`,
    { query: contextQuery(session) },
  );
}

export async function uploadAttachment(
  session: AgentSession,
  requestId: string,
  file: File,
): Promise<ChatAttachment> {
  const form = new FormData();
  form.set("conversation_id", session.conversation_id);
  form.set("tenant_id", session.tenant_id);
  form.set("active_organization_unit_id", session.active_organization_unit_id);
  form.set("principal_id", session.principal_id);
  form.set("principal_type", session.principal_type);
  form.set("request_id", requestId);
  form.set("file", file);
  return fetchJson<ChatAttachment>("/api/agent/chat/attachments", {
    method: "POST",
    body: form,
  });
}

export function attachmentUrl(session: AgentSession, attachmentId: string): string {
  return apiUrl(
    `/api/agent/chat/attachments/${encodeURIComponent(attachmentId)}`,
    { ...contextQuery(session), conversation_id: session.conversation_id },
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
    },
    body: JSON.stringify(body),
    signal,
  });
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
    "/api/agent/chat/stream",
    {
      ...payload.session,
      content: payload.content,
      attachment_ids: payload.attachmentIds,
      request_id: payload.requestId,
      slash_target: payload.slashTarget,
      metadata: {},
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
    "/api/agent/chat/ask-answer",
    {
      ...payload.session,
      request_id: payload.requestId,
      ask_id: payload.askId,
      status: payload.status,
      answers: payload.answers,
      metadata: {},
    },
    payload.signal,
    payload.onEvent,
  );
}

export async function interruptConversation(session: AgentSession): Promise<boolean> {
  const response = await fetchJson<{ interrupted: boolean }>(
    `/api/agent/conversations/${encodeURIComponent(session.conversation_id)}/interrupt`,
    {
      method: "POST",
      body: JSON.stringify(session),
    },
  );
  return response.interrupted;
}

export function interruptConversationKeepalive(session: AgentSession): void {
  const path = `/api/agent/conversations/${encodeURIComponent(session.conversation_id)}/interrupt`;
  const body = new Blob([JSON.stringify(session)], { type: "application/json" });
  if (navigator.sendBeacon?.(apiUrl(path), body)) return;
  void fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => undefined);
}
