export interface AgentSession {
  conversation_id: string;
  tenant_id: string;
  active_organization_unit_id: string;
  principal_id: string;
  principal_type: string;
}

export interface SlashTarget {
  kind: "skill" | "scene";
  asset_key: string;
  name: string;
}

export interface SlashCandidate extends SlashTarget {
  description: string;
}

export interface ChatCapabilities {
  support_vision: boolean;
  max_image_bytes: number;
  max_images_per_message: number;
  accepted_mime_types: string[];
}

export interface ChatAttachment {
  attachment_id: string;
  conversation_id: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  preview_url?: string;
}

export type MessageKind =
  | "input"
  | "meta"
  | "system"
  | "assistant"
  | "tool_use"
  | "tool_result"
  | "ask"
  | "error"
  | "memory_compaction";

export interface ChatMessage {
  message_id: string;
  conversation_id: string;
  role: string;
  kind: MessageKind;
  content: string;
  payload: Record<string, unknown>;
  run_id: string;
  request_id: string;
  sequence?: number;
  created_at?: string;
  transient?: boolean;
}

export interface MessagePage {
  conversation_id: string;
  messages: ChatMessage[];
  has_more: boolean;
  next_before_sequence: number | null;
  run_state: string | null;
  pending_ask: Record<string, unknown> | null;
}

export interface ConversationState {
  conversation_id: string;
  run_state: string | null;
  run_id: string | null;
  pending_ask: Record<string, unknown> | null;
}

export interface AskOption {
  label: string;
  description: string;
  preview?: string | null;
}

export interface AskQuestion {
  question: string;
  header: string;
  options: AskOption[];
  multiSelect: boolean;
}

export interface PendingAsk {
  askId: string;
  toolCallId: string;
  questions: AskQuestion[];
  timeoutSeconds: number;
  expiresAt?: string;
}

export interface StreamEvent {
  event: string;
  data: Record<string, unknown>;
}
