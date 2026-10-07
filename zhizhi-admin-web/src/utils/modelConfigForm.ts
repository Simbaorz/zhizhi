export function modelConfigFields(
  generation?: Record<string, unknown>,
  provider: Record<string, unknown> = {},
) {
  const value = (input: unknown, fallback: string) => input == null ? fallback : String(input);
  const generationValue = (key: string, fallback: string) => value(generation?.[key], generation ? "" : fallback);
  return {
    contextWindow: value(provider.context_window, "32768"),
    temperature: generationValue("temperature", "0.7"),
    topP: generationValue("top_p", "1"),
    maxTokens: generationValue("max_tokens", "4096"),
    presencePenalty: generationValue("presence_penalty", "0"),
    frequencyPenalty: generationValue("frequency_penalty", "0"),
    seed: generationValue("seed", ""),
  };
}

export function buildModelConfigs(
  form: ReturnType<typeof modelConfigFields>,
  existingGeneration: Record<string, unknown> = {},
  existingProvider: Record<string, unknown> = {},
) {
  const generationConfig = { ...existingGeneration };
  const fields = [
    ["temperature", "temperature", 0, 2, false],
    ["topP", "top_p", 0, 1, false],
    ["maxTokens", "max_tokens", 1, Infinity, true],
    ["presencePenalty", "presence_penalty", -2, 2, false],
    ["frequencyPenalty", "frequency_penalty", -2, 2, false],
    ["seed", "seed", 0, Infinity, true],
  ] as const;
  for (const [field, key, min, max, integer] of fields) {
    const text = form[field].trim();
    delete generationConfig[key];
    if (text) generationConfig[key] = numericValue(text, key, min, max, integer);
  }
  const providerConfig = {
    ...existingProvider,
    context_window: numericValue(form.contextWindow.trim(), "上下文窗口", 1, Infinity, true),
  };
  return { generationConfig, providerConfig };
}

function numericValue(text: string, label: string, min: number, max: number, integer: boolean): number {
  const value = Number(text);
  if (!text || !Number.isFinite(value) || value < min || value > max || (integer && !Number.isSafeInteger(value))) {
    const range = max === Infinity ? `不得小于 ${min}` : `范围为 ${min} 至 ${max}`;
    throw new Error(`${label}必须是有效的${integer ? "整数" : "数字"}，${range}`);
  }
  return value;
}
