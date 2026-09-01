import type { AgentSession } from "@/types";

const STORAGE_KEY = "zhizhi-web-temporary-session-v1";

export function createDefaultSession(now = new Date()): AgentSession {
  const stamp = now
    .toISOString()
    .replace(/[-:TZ.]/g, "")
    .slice(0, 14);
  return {
    conversation_id: `conversation-${stamp}`,
    tenant_id: "",
    active_organization_unit_id: "",
    principal_id: "",
    principal_type: "user",
  };
}

export function normalizeSession(value: AgentSession): AgentSession {
  return {
    conversation_id: value.conversation_id.trim(),
    tenant_id: value.tenant_id.trim(),
    active_organization_unit_id: value.active_organization_unit_id.trim(),
    principal_id: value.principal_id.trim(),
    principal_type: value.principal_type.trim() || "user",
  };
}

export function isValidAgentSession(value: unknown): value is AgentSession {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const session = value as Record<string, unknown>;
  return (
    ["conversation_id", "tenant_id", "principal_id", "principal_type"].every(
      (key) => typeof session[key] === "string" && session[key].trim().length > 0,
    )
    && typeof session.active_organization_unit_id === "string"
  );
}

export function loadTemporarySession(): AgentSession | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isValidAgentSession(parsed)) return null;
    return normalizeSession(parsed);
  } catch {
    return null;
  }
}

export function saveTemporarySession(session: AgentSession): void {
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(normalizeSession(session)));
}

export function clearTemporarySession(): void {
  window.sessionStorage.removeItem(STORAGE_KEY);
}
