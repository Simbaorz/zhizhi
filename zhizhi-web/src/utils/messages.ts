import type { ChatMessage } from "@/types";

export interface NormalizedToolResultEvent {
  result: Record<string, unknown>;
  isError: boolean;
}

export interface SlashTargetPresentation {
  kind: "skill" | "scene";
  name: string;
  label: "技能" | "场景";
}

export function normalizeToolResultEvent(value: unknown): NormalizedToolResultEvent {
  const wrapper = recordValue(value);
  const output = Object.hasOwn(wrapper, "output") ? wrapper.output : wrapper;
  const result = recordOrValue(output);
  return {
    result,
    isError: Boolean(wrapper.is_error || result.error),
  };
}

export function slashTargetPresentation(value: unknown): SlashTargetPresentation | null {
  const target = recordValue(value);
  const kind = stringValue(target.kind);
  if (kind !== "skill" && kind !== "scene") return null;
  const name = stringValue(target.name || target.asset_key).trim();
  if (!name) return null;
  return {
    kind,
    name,
    label: kind === "skill" ? "技能" : "场景",
  };
}

export function isInterruptedRunMessage(message: ChatMessage): boolean {
  const payload = message.payload || {};
  if (stringValue(payload.code) === "cancelled") return true;
  return false;
}

export function buildDisplayMessages(messages: ChatMessage[]): ChatMessage[] {
  const display: ChatMessage[] = [];
  const toolResults = new Map<string, ChatMessage>();
  const toolUseIds = new Set<string>();
  const completedCompactionIds = new Set<string>();

  messages.forEach((message) => {
    if (message.kind === "memory_compaction" && message.payload.phase === "completed") {
      const compactionId = stringValue(message.payload.compaction_id);
      if (compactionId) completedCompactionIds.add(compactionId);
    }
    if (isMergeableToolUse(message)) {
      toolUseIds.add(toolCallId(message));
      return;
    }
    if (isMergeableToolResult(message)) {
      toolResults.set(toolCallId(message), message);
    }
  });

  messages.forEach((message, index) => {
    if (message.kind === "meta") return;
    if (message.kind === "assistant" && !message.content.trim()) return;
    if (
      message.kind === "memory_compaction"
      && message.payload.phase === "started"
      && completedCompactionIds.has(stringValue(message.payload.compaction_id))
    ) {
      return;
    }
    if (isAskUserToolUse(message) || isAskUserToolResult(message)) return;
    if (isMergeableToolResult(message) && toolUseIds.has(toolCallId(message))) return;
    if (message.kind === "ask") {
      display.push(askThreadMessage(message, messages, index));
      return;
    }
    if (isMergeableToolUse(message)) {
      display.push(toolDisplayMessage(message, toolResults.get(toolCallId(message))));
      return;
    }
    display.push(message);
  });
  return display;
}

function toolDisplayMessage(
  toolUse: ChatMessage,
  toolResult: ChatMessage | undefined,
): ChatMessage {
  const isSkill = toolUse.payload.tool_name === "skill";
  return {
    ...toolUse,
    payload: {
      ...toolUse.payload,
      tool_display: true,
      ...(toolResult
        ? {
            tool_result: toolResult.payload.result,
            tool_is_error: Boolean(toolResult.payload.is_error),
            tool_result_message_id: toolResult.message_id,
          }
        : {}),
      ...(isSkill
        ? {
            skill_tool_display: true,
            ...(toolResult
              ? {
                  skill_tool_result: toolResult.payload.result,
                  skill_tool_is_error: Boolean(toolResult.payload.is_error),
                  skill_tool_result_message_id: toolResult.message_id,
                }
              : {}),
          }
        : {}),
    },
  };
}

function askThreadMessage(
  askQuestion: ChatMessage,
  messages: ChatMessage[],
  askIndex: number,
): ChatMessage {
  const toolCallId = stringValue(askQuestion.payload.tool_call_id);
  const resultMessage = messages.find(
    (message) => isAskUserToolResult(message) && stringValue(message.payload.tool_call_id) === toolCallId,
  );
  const result = recordValue(resultMessage?.payload.result);
  const answers = recordValue(result.answers);
  const metadata = recordValue(result.metadata);
  const inferredSkipped = !resultMessage && hasLaterUserMessage(messages, askIndex);
  const skipped =
    metadata.status === "skipped"
    || metadata.skipped === true
    || inferredSkipped
    || stringValue(result.error).includes("cancelled");
  const status = resultMessage ? (skipped ? "skipped" : "answered") : inferredSkipped ? "skipped" : "pending";
  const questions = Array.isArray(askQuestion.payload.questions) ? askQuestion.payload.questions : [];
  return {
    ...askQuestion,
    role: "system",
    kind: "ask",
    content: "",
    payload: {
      ...askQuestion.payload,
      ask_history_thread: {
        toolCallId,
        askId: stringValue(askQuestion.payload.ask_id),
        status,
        questions: questions.map((item, index) => {
          const question = recordValue(item);
          const key = stringValue(question.question || question.header || `question_${index + 1}`);
          const text = stringValue(question.question || question.header || `问题 ${index + 1}`);
          const answer = answerText(answers[key]);
          return {
            question: text,
            header: stringValue(question.header),
            answer,
            status: answer ? "answered" : status === "pending" ? "pending" : "skipped",
          };
        }),
      },
    },
  };
}

function isMergeableToolUse(message: ChatMessage): boolean {
  return message.kind === "tool_use" && !isAskUserToolName(message.payload.tool_name) && Boolean(toolCallId(message));
}

function isMergeableToolResult(message: ChatMessage): boolean {
  return message.kind === "tool_result" && !isAskUserToolName(message.payload.tool_name) && Boolean(toolCallId(message));
}

function isAskUserToolUse(message: ChatMessage): boolean {
  return message.kind === "tool_use" && isAskUserToolName(message.payload.tool_name);
}

function isAskUserToolResult(message: ChatMessage): boolean {
  return message.kind === "tool_result" && isAskUserToolName(message.payload.tool_name);
}

function isAskUserToolName(value: unknown): boolean {
  return value === "ask_user";
}

function toolCallId(message: ChatMessage): string {
  return stringValue(message.payload.tool_call_id);
}

function hasLaterUserMessage(messages: ChatMessage[], askIndex: number): boolean {
  return messages.slice(askIndex + 1).some((message) => message.kind === "input");
}

function answerText(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => stringValue(item)).filter(Boolean).join("、");
  return stringValue(value).trim();
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function recordOrValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : { value };
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : value === null || value === undefined ? "" : String(value);
}
