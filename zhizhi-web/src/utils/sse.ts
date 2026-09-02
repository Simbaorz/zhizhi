import type { StreamEvent } from "@/types";

export function parseSseFrame(rawFrame: string): StreamEvent | null {
  const lines = rawFrame.replace(/\r\n/g, "\n").split("\n");
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim() || "message";
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (!dataLines.length) return null;
  try {
    const parsed: unknown = JSON.parse(dataLines.join("\n"));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    return { event, data: parsed as Record<string, unknown> };
  } catch {
    return null;
  }
}

export async function readSseStream(
  response: Response,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  if (!response.body) throw new Error("服务器未返回可读取的消息流。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = parseSseFrame(frame);
      if (event) onEvent(event);
    }
    if (done) break;
  }

  const finalEvent = parseSseFrame(buffer);
  if (finalEvent) onEvent(finalEvent);
}
