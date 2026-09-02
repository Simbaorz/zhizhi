import type { ChatMessage } from "@/types";

export function buildDisplayMessages(messages: ChatMessage[]): ChatMessage[] {
  const result: ChatMessage[] = [];
  const toolUseIndexes = new Map<string, number>();
  const compactionIndexes = new Map<string, number>();

  for (const message of messages) {
    const toolName = textValue(message.payload.tool_name);
    const toolCallId = textValue(message.payload.tool_call_id);
    if (toolName === "ask_user" && ["tool_use", "tool_result"].includes(message.kind)) {
      continue;
    }

    if (message.kind === "tool_use" && toolCallId) {
      toolUseIndexes.set(toolCallId, result.length);
      result.push(message);
      continue;
    }
    if (message.kind === "tool_result" && toolCallId) {
      const index = toolUseIndexes.get(toolCallId);
      if (index !== undefined) {
        result[index] = {
          ...result[index],
          payload: {
            ...result[index].payload,
            tool_result: message.payload.result,
            tool_is_error: message.payload.is_error,
          },
        };
        continue;
      }
    }

    if (message.kind === "memory_compaction") {
      const compactionId = textValue(message.payload.compaction_id);
      const previousIndex = compactionIndexes.get(compactionId);
      if (compactionId && previousIndex !== undefined) {
        result[previousIndex] = message;
        continue;
      }
      if (compactionId) compactionIndexes.set(compactionId, result.length);
    }
    result.push(message);
  }
  return result;
}

function textValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
