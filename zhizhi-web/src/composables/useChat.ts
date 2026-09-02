import { computed, onBeforeUnmount, ref } from "vue";

import {
  answerAsk,
  ApiError,
  attachmentUrl,
  getCapabilities,
  getConversationState,
  getMessages,
  getScenes,
  getSkills,
  interruptConversation,
  interruptConversationKeepalive,
  streamChat,
  uploadAttachment,
} from "@/api/client";
import type {
  AskQuestion,
  ChatAttachment,
  ChatCapabilities,
  ChatMessage,
  AgentSession,
  MessagePage,
  PendingAsk,
  SlashCandidate,
  SlashTarget,
  StreamEvent,
} from "@/types";

const DEFAULT_CAPABILITIES: ChatCapabilities = {
  support_vision: false,
  max_image_bytes: 5 * 1024 * 1024,
  max_images_per_message: 4,
  accepted_mime_types: ["image/jpeg", "image/png"],
};

export function useChat() {
  const session = ref<AgentSession | null>(null);
  const messages = ref<ChatMessage[]>([]);
  const skills = ref<SlashCandidate[]>([]);
  const scenes = ref<SlashCandidate[]>([]);
  const capabilities = ref<ChatCapabilities>(DEFAULT_CAPABILITIES);
  const capabilitiesLoaded = ref(false);
  const pendingAsk = ref<PendingAsk | null>(null);
  const runState = ref<string | null>(null);
  const loading = ref(false);
  const loadingOlder = ref(false);
  const streaming = ref(false);
  const errorMessage = ref("");
  const hasMoreMessages = ref(false);
  const nextBeforeSequence = ref<number | null>(null);
  let activeController: AbortController | null = null;

  const targets = computed(() => [...skills.value, ...scenes.value]);
  const imageSupportStatus = computed<"loading" | "supported" | "unsupported" | "error">(
    () => {
      if (!capabilitiesLoaded.value) return errorMessage.value ? "error" : "loading";
      return capabilities.value.support_vision ? "supported" : "unsupported";
    },
  );

  async function bootstrap(nextSession: AgentSession): Promise<void> {
    session.value = nextSession;
    messages.value = [];
    skills.value = [];
    scenes.value = [];
    pendingAsk.value = null;
    runState.value = null;
    errorMessage.value = "";
    capabilities.value = DEFAULT_CAPABILITIES;
    capabilitiesLoaded.value = false;
    loading.value = true;

    const [capabilityResult, skillsResult, scenesResult, messagesResult, stateResult] =
      await Promise.allSettled([
        getCapabilities(nextSession),
        getSkills(nextSession),
        getScenes(nextSession),
        getMessages(nextSession),
        getConversationState(nextSession),
      ]);

    const errors: string[] = [];
    if (capabilityResult.status === "fulfilled") {
      capabilities.value = capabilityResult.value;
      capabilitiesLoaded.value = true;
    } else {
      errors.push(errorText(capabilityResult.reason, "模型能力加载失败"));
    }
    if (skillsResult.status === "fulfilled") skills.value = skillsResult.value;
    else errors.push(errorText(skillsResult.reason, "Skill 加载失败"));
    if (scenesResult.status === "fulfilled") scenes.value = scenesResult.value;
    else errors.push(errorText(scenesResult.reason, "Scene 加载失败"));
    if (messagesResult.status === "fulfilled") applyMessagePage(messagesResult.value);
    else errors.push(errorText(messagesResult.reason, "历史消息加载失败"));
    if (stateResult.status === "fulfilled") {
      runState.value = stateResult.value.run_state;
      pendingAsk.value = pendingAskFromPayload(stateResult.value.pending_ask);
    } else {
      errors.push(errorText(stateResult.reason, "会话状态加载失败"));
    }
    errorMessage.value = unique(errors).join("；");
    loading.value = false;
  }

  async function refreshCatalogs(): Promise<void> {
    const current = session.value;
    if (!current) return;
    const [skillResult, sceneResult] = await Promise.allSettled([
      getSkills(current),
      getScenes(current),
    ]);
    if (skillResult.status === "fulfilled") skills.value = skillResult.value;
    if (sceneResult.status === "fulfilled") scenes.value = sceneResult.value;
  }

  async function loadOlderMessages(): Promise<void> {
    const current = session.value;
    const beforeSequence = nextBeforeSequence.value;
    if (!current || !beforeSequence || loadingOlder.value || !hasMoreMessages.value) return;
    loadingOlder.value = true;
    try {
      const page = await getMessages(current, beforeSequence);
      const existingIds = new Set(messages.value.map((message) => message.message_id));
      messages.value = [
        ...page.messages.filter((message) => !existingIds.has(message.message_id)),
        ...messages.value,
      ];
      hasMoreMessages.value = page.has_more;
      nextBeforeSequence.value = page.next_before_sequence;
    } catch (error) {
      errorMessage.value = errorText(error, "更早消息加载失败");
    } finally {
      loadingOlder.value = false;
    }
  }

  async function sendMessage(
    content: string,
    files: File[],
    slashTarget: SlashTarget | null,
  ): Promise<void> {
    const current = session.value;
    if (!current || streaming.value) return;
    const requestId = createClientId();
    errorMessage.value = "";
    streaming.value = true;
    runState.value = "running";
    pendingAsk.value = null;
    activeController = new AbortController();

    let attachments: ChatAttachment[] = [];
    try {
      attachments = files.length
        ? await Promise.all(
            files.map(async (file) => {
              const attachment = await uploadAttachment(current, requestId, file);
              return {
                ...attachment,
                preview_url: attachmentUrl(current, attachment.attachment_id),
              };
            }),
          )
        : [];

      messages.value.push({
        message_id: requestId,
        conversation_id: current.conversation_id,
        role: "user",
        kind: "input",
        content,
        payload: {
          attachments,
          ...(slashTarget ? { slash_target: slashTarget } : {}),
        },
        run_id: "",
        request_id: requestId,
        created_at: new Date().toISOString(),
        transient: true,
      });

      await streamChat({
        session: current,
        content,
        attachmentIds: attachments.map((item) => item.attachment_id),
        requestId,
        slashTarget,
        signal: activeController.signal,
        onEvent: applyStreamEvent,
      });
      await refreshAuthoritativeState();
    } catch (error) {
      if (!isAbortError(error)) {
        errorMessage.value = errorText(error, "消息发送失败");
        appendErrorMessage(errorMessage.value, requestId);
      }
    } finally {
      activeController = null;
      streaming.value = false;
      if (runState.value === "running") runState.value = "completed";
    }
  }

  async function submitAsk(
    answers: Record<string, string | string[]>,
    status: "answered" | "skipped",
  ): Promise<void> {
    const current = session.value;
    const ask = pendingAsk.value;
    if (!current || !ask || streaming.value) return;
    const requestId = createClientId();
    pendingAsk.value = null;
    errorMessage.value = "";
    streaming.value = true;
    runState.value = "running";
    activeController = new AbortController();
    try {
      await answerAsk({
        session: current,
        askId: ask.askId,
        answers,
        status,
        requestId,
        signal: activeController.signal,
        onEvent: applyStreamEvent,
      });
      await refreshAuthoritativeState();
    } catch (error) {
      if (!isAbortError(error)) {
        errorMessage.value = errorText(error, "补充信息提交失败");
        pendingAsk.value = ask;
      }
    } finally {
      activeController = null;
      streaming.value = false;
    }
  }

  async function interrupt(): Promise<void> {
    const current = session.value;
    if (!current) return;
    activeController?.abort();
    activeController = null;
    try {
      await interruptConversation(current);
      runState.value = "cancelled";
      pendingAsk.value = null;
    } catch (error) {
      errorMessage.value = errorText(error, "停止输出失败");
    } finally {
      streaming.value = false;
    }
  }

  function interruptKeepalive(): void {
    const current = session.value;
    if (!current || (!streaming.value && !pendingAsk.value)) return;
    activeController?.abort();
    interruptConversationKeepalive(current);
  }

  function reset(): void {
    activeController?.abort();
    activeController = null;
    session.value = null;
    messages.value = [];
    skills.value = [];
    scenes.value = [];
    pendingAsk.value = null;
    runState.value = null;
    loading.value = false;
    loadingOlder.value = false;
    streaming.value = false;
    errorMessage.value = "";
    hasMoreMessages.value = false;
    nextBeforeSequence.value = null;
  }

  async function refreshAuthoritativeState(): Promise<void> {
    const current = session.value;
    if (!current) return;
    const [messageResult, stateResult] = await Promise.allSettled([
      getMessages(current),
      getConversationState(current),
    ]);
    if (messageResult.status === "fulfilled") applyMessagePage(messageResult.value);
    if (stateResult.status === "fulfilled") {
      runState.value = stateResult.value.run_state;
      pendingAsk.value = pendingAskFromPayload(stateResult.value.pending_ask);
    }
  }

  function applyMessagePage(page: MessagePage): void {
    messages.value = page.messages;
    hasMoreMessages.value = page.has_more;
    nextBeforeSequence.value = page.next_before_sequence;
    runState.value = page.run_state;
    pendingAsk.value = pendingAskFromPayload(page.pending_ask);
  }

  function applyStreamEvent(streamEvent: StreamEvent): void {
    const current = session.value;
    if (!current || streamEvent.event === "done") return;
    const data = streamEvent.data;
    const messageId = stringValue(data.message_id) || createClientId();
    const requestId = stringValue(data.request_id);
    const conversationId = stringValue(data.conversation_id) || current.conversation_id;
    const base = {
      message_id: messageId,
      conversation_id: conversationId,
      run_id: stringValue(data.run_id),
      request_id: requestId,
      created_at: new Date().toISOString(),
      transient: true,
    };

    if (streamEvent.event === "assistant_delta") {
      upsertAssistant({ ...base, content: stringValue(data.content) }, true);
      return;
    }
    if (streamEvent.event === "assistant_intermediate") {
      upsertAssistant({ ...base, content: stringValue(data.content) }, false, true);
      return;
    }
    if (streamEvent.event === "assistant_final") {
      upsertAssistant({ ...base, content: stringValue(data.content) }, false);
      return;
    }
    if (streamEvent.event === "tool_use") {
      const call = recordValue(data.call);
      messages.value.push({
        ...base,
        role: "assistant",
        kind: "tool_use",
        content: stringValue(data.assistant_text),
        payload: {
          tool_call_id: stringValue(call.tool_call_id),
          tool_name: stringValue(call.name),
          arguments: recordValue(call.arguments),
        },
      });
      return;
    }
    if (streamEvent.event === "tool_result") {
      const call = recordValue(data.call);
      const result = recordValue(data.result);
      messages.value.push({
        ...base,
        role: "tool",
        kind: "tool_result",
        content: stringValue(result.error),
        payload: {
          tool_call_id: stringValue(call.tool_call_id),
          tool_name: stringValue(call.name),
          result,
          is_error: Boolean(result.is_error || result.error),
        },
      });
      return;
    }
    if (streamEvent.event === "ask_requested") {
      const call = recordValue(data.call);
      const payload = {
        ask_id: stringValue(data.ask_id),
        tool_call_id: stringValue(call.tool_call_id),
        questions: data.questions,
        timeout_seconds: numberValue(data.timeout_seconds),
      };
      messages.value.push({
        ...base,
        role: "assistant",
        kind: "ask",
        content: "",
        payload,
      });
      pendingAsk.value = pendingAskFromPayload(payload);
      runState.value = "waiting_input";
      return;
    }
    if (streamEvent.event === "memory_compaction") {
      const phase = stringValue(data.phase);
      const compactionId = stringValue(data.compaction_id);
      if (phase === "cancelled") {
        messages.value = messages.value.filter(
          (message) => stringValue(message.payload.compaction_id) !== compactionId,
        );
        return;
      }
      messages.value.push({
        ...base,
        role: "system",
        kind: "memory_compaction",
        content: stringValue(data.content),
        payload: { phase, compaction_id: compactionId },
      });
      return;
    }
    if (streamEvent.event === "error") {
      const message = stringValue(data.message) || "智能体执行失败。";
      appendErrorMessage(message, requestId, messageId);
    }
  }

  function upsertAssistant(
    base: Pick<
      ChatMessage,
      | "message_id"
      | "conversation_id"
      | "run_id"
      | "request_id"
      | "created_at"
      | "transient"
      | "content"
    >,
    append: boolean,
    intermediate = false,
  ): void {
    const index = messages.value.findIndex((message) => message.message_id === base.message_id);
    if (index >= 0) {
      const current = messages.value[index];
      messages.value[index] = {
        ...current,
        content: append ? `${current.content}${base.content}` : base.content,
        payload: { final: !append, llm_ignore: intermediate },
      };
      return;
    }
    messages.value.push({
      ...base,
      role: "assistant",
      kind: "assistant",
      payload: { final: !append, llm_ignore: intermediate },
    });
  }

  function appendErrorMessage(content: string, requestId: string, messageId = createClientId()): void {
    messages.value.push({
      message_id: messageId,
      conversation_id: session.value?.conversation_id ?? "",
      role: "assistant",
      kind: "error",
      content,
      payload: { error: content },
      run_id: "",
      request_id: requestId,
      created_at: new Date().toISOString(),
      transient: true,
    });
  }

  onBeforeUnmount(() => activeController?.abort());

  return {
    session,
    messages,
    skills,
    scenes,
    targets,
    capabilities,
    imageSupportStatus,
    pendingAsk,
    runState,
    loading,
    loadingOlder,
    streaming,
    errorMessage,
    hasMoreMessages,
    bootstrap,
    refreshCatalogs,
    loadOlderMessages,
    sendMessage,
    submitAsk,
    interrupt,
    interruptKeepalive,
    reset,
  };
}

function pendingAskFromPayload(payload: Record<string, unknown> | null): PendingAsk | null {
  if (!payload) return null;
  const askId = stringValue(payload.ask_id);
  const questions = questionList(payload.questions);
  if (!askId || !questions.length) return null;
  return {
    askId,
    toolCallId: stringValue(payload.tool_call_id),
    questions,
    timeoutSeconds: numberValue(payload.timeout_seconds),
    expiresAt: stringValue(payload.expires_at) || undefined,
  };
}

function questionList(value: unknown): AskQuestion[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const question = recordValue(item);
    return {
      question: stringValue(question.question),
      header: stringValue(question.header),
      multiSelect: question.multiSelect === true,
      options: Array.isArray(question.options)
        ? question.options.map((option) => {
            const entry = recordValue(option);
            return {
              label: stringValue(entry.label),
              description: stringValue(entry.description),
              preview: entry.preview === null ? null : stringValue(entry.preview),
            };
          })
        : [],
    };
  });
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function numberValue(value: unknown): number {
  return typeof value === "number" ? value : Number(value || 0);
}

function errorText(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.code) return `${error.message}（${error.code}）`;
  return error instanceof Error && error.message ? error.message : fallback;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function createClientId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
