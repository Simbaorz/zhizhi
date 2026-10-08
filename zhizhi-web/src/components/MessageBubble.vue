<script setup lang="ts">
import {
  ArrowDown,
  ArrowRight,
  CircleCheck,
  Loading,
  QuestionFilled,
  Service,
  Tools,
  Warning,
} from "@element-plus/icons-vue";
import { computed, ref } from "vue";

import { attachmentUrl } from "@/api/client";
import MarkdownPreview from "@/components/MarkdownPreview.vue";
import type { ChatAttachment, ChatMessage, AgentSession, SlashTarget } from "@/types";

const props = defineProps<{
  message: ChatMessage;
  session: AgentSession;
}>();

const expanded = ref(false);
const isUser = computed(() => props.message.kind === "input" || props.message.role === "user");
const isAssistant = computed(() => props.message.kind === "assistant");
const isTool = computed(() => props.message.kind === "tool_use" || props.message.kind === "tool_result");
const isAsk = computed(() => props.message.kind === "ask");
const askThread = computed(() => recordValue(props.message.payload.ask_history_thread));
const askHistory = computed(() => Array.isArray(askThread.value.questions) ? askThread.value.questions.map(recordValue) : []);
const isError = computed(() => props.message.kind === "error");
const isCompaction = computed(() => props.message.kind === "memory_compaction");
const compactionStarted = computed(
  () => isCompaction.value && textValue(props.message.payload.phase) === "started",
);
const attachments = computed(() => parseAttachments(props.message.payload.attachments));
const slashTarget = computed(() => parseSlashTarget(props.message.payload.slash_target));
const toolName = computed(() => textValue(props.message.payload.tool_name) || "工具");
const toolTitle = computed(() => ({ list: "浏览目录", read: "读取文件", glob: "查找文件", grep: "搜索内容", skill: "调用技能", query_business_data: "查询业务数据" } as Record<string, string>)[toolName.value] || toolName.value);
const toolArguments = computed(() => recordValue(props.message.payload.arguments));
const toolResult = computed(() => recordValue(props.message.payload.tool_result ?? props.message.payload.result));
const hasToolResult = computed(
  () => Object.hasOwn(props.message.payload, "tool_result") || props.message.kind === "tool_result",
);
const toolFailed = computed(() => Boolean(props.message.payload.tool_is_error || props.message.payload.is_error));
const toolSummary = computed(() => {
  if (!hasToolResult.value) return "智能体正在执行";
  if (toolFailed.value) return "执行未完成";
  if (toolName.value === "query_business_data" && typeof toolResult.value.row_count === "number") return `返回 ${toolResult.value.row_count} 行${toolResult.value.truncated ? '（已截断）' : ''}`;
  if (toolName.value === "read" && typeof toolResult.value.num_lines === "number") return `读取 ${toolResult.value.num_lines} 行`;
  return "执行完成";
});
const queryColumns = computed(() => Array.isArray(toolResult.value.columns) ? toolResult.value.columns.filter((item): item is string => typeof item === 'string') : []);
const queryRows = computed(() => Array.isArray(toolResult.value.rows) ? toolResult.value.rows.filter(Array.isArray).slice(0, 50) : []);
const askQuestions = computed(() => (Array.isArray(props.message.payload.questions) ? props.message.payload.questions : []));
const attachmentViews = computed(() =>
  attachments.value.map((attachment) => ({
    ...attachment,
    url: attachment.preview_url || attachmentUrl(props.session, attachment.attachment_id),
  })),
);

function prettyJson(value: Record<string, unknown>): string {
  return Object.keys(value).length ? JSON.stringify(value, null, 2) : "暂无详细信息";
}

function parseAttachments(value: unknown): ChatAttachment[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const entry = recordValue(item);
    const attachmentId = textValue(entry.attachment_id);
    if (!attachmentId) return [];
    return [
      {
        attachment_id: attachmentId,
        conversation_id: textValue(entry.conversation_id),
        original_name: textValue(entry.original_name) || "图片附件",
        mime_type: textValue(entry.mime_type),
        size_bytes: numberValue(entry.size_bytes),
        preview_url: textValue(entry.preview_url) || undefined,
      },
    ];
  });
}

function parseSlashTarget(value: unknown): SlashTarget | null {
  const entry = recordValue(value);
  const kind = textValue(entry.kind);
  if (kind !== "skill" && kind !== "scene") return null;
  return {
    kind,
    asset_key: textValue(entry.asset_key),
    name: textValue(entry.name),
  };
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function textValue(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function numberValue(value: unknown): number {
  return typeof value === "number" ? value : Number(value || 0);
}
</script>

<template>
  <article
    class="message-row"
    :class="{
      'message-row-user': isUser,
      'message-row-assistant': isAssistant,
      'message-row-tool': isTool,
      'message-row-error': isError,
      'message-row-ask': isAsk,
      'message-row-compaction': isCompaction,
    }"
  >
    <el-avatar
      v-if="!isUser && !isCompaction"
      class="message-avatar"
      :class="{ 'message-avatar-tool': isTool, 'message-avatar-warning': isError }"
      :size="34"
      shape="square"
    >
      <el-icon :size="18">
        <Tools v-if="isTool" />
        <QuestionFilled v-else-if="isAsk" />
        <Warning v-else-if="isError" />
        <Service v-else />
      </el-icon>
    </el-avatar>

    <el-card v-if="isUser" class="user-message-card" shadow="never">
      <div v-if="slashTarget" class="user-target-context">
        <span>{{ slashTarget.kind === "skill" ? "技能" : "场景" }}</span>
        <strong>/{{ slashTarget.name }}</strong>
      </div>
      <p v-if="message.content" class="user-message-text">{{ message.content }}</p>
      <div v-if="attachmentViews.length" class="user-attachment-grid">
        <a
          v-for="attachment in attachmentViews"
          :key="attachment.attachment_id"
          class="user-attachment-image"
          :href="attachment.url"
          target="_blank"
          rel="noreferrer"
          :title="attachment.original_name"
        >
          <img :src="attachment.url" :alt="attachment.original_name" loading="lazy" />
        </a>
      </div>
    </el-card>

    <div
      v-else-if="isCompaction"
      class="memory-compaction-status"
      :class="{ completed: !compactionStarted }"
      role="status"
    >
      <el-icon :class="{ 'is-loading': compactionStarted }">
        <Loading v-if="compactionStarted" />
        <CircleCheck v-else />
      </el-icon>
      <span>{{ message.content || (compactionStarted ? "正在整理对话上下文" : "对话上下文已整理") }}</span>
    </div>

    <el-card v-else-if="isAssistant" class="assistant-message-card" shadow="never">
      <MarkdownPreview :model-value="message.content" />
    </el-card>

    <el-card
      v-else-if="isTool"
      class="tool-message-card"
      :class="{ danger: toolFailed }"
      shadow="never"
    >
      <el-button class="tool-message-summary" @click="expanded = !expanded">
        <span class="tool-message-copy">
          <strong>{{ toolTitle }}</strong>
          <small>{{ toolSummary }}</small>
        </span>
        <el-icon>
          <ArrowDown v-if="expanded" />
          <ArrowRight v-else />
        </el-icon>
      </el-button>
      <div v-if="expanded" class="tool-message-detail">
        <section>
          <span>请求参数</span>
          <pre>{{ prettyJson(toolArguments) }}</pre>
        </section>
        <section v-if="hasToolResult">
          <span>执行结果</span>
          <div v-if="toolName === 'query_business_data' && queryColumns.length" class="business-result"><table><thead><tr><th v-for="column in queryColumns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in queryRows" :key="index"><td v-for="(cell, column) in row" :key="column">{{ cell == null ? '—' : typeof cell === 'object' ? JSON.stringify(cell) : cell }}</td></tr></tbody></table><small v-if="(toolResult.rows as unknown[]).length > 50">仅展示前 50 行</small></div>
          <pre v-else>{{ prettyJson(toolResult) }}</pre>
        </section>
      </div>
    </el-card>

    <el-card v-else-if="isAsk" class="ask-message-card" shadow="never">
      <strong>{{ askThread.status === 'answered' ? '已补充信息' : askThread.status === 'skipped' ? '已跳过补充' : '需要补充信息' }}</strong>
      <section v-for="(item, index) in askHistory" :key="index"><p>{{ item.question }}</p><span>{{ item.answer || (item.status === 'pending' ? '等待回答' : '已跳过') }}</span></section>
      <span v-if="!askHistory.length">智能体正在询问 {{ askQuestions.length || 1 }} 个问题</span>
    </el-card>

    <el-card v-else class="system-message-card" :class="{ danger: isError }" shadow="never">
      <el-icon><Warning v-if="isError" /><QuestionFilled v-else /></el-icon>
      <span>{{ message.content || "系统消息" }}</span>
    </el-card>
  </article>
</template>

<style scoped>
.business-result { max-height: 280px; overflow: auto; }.business-result table { border-collapse: collapse; min-width: 100%; font-size: 12px; }.business-result th,.business-result td { padding: 8px 12px; text-align: left; border: 1px solid var(--border-weak); white-space: nowrap; }.business-result th { background: #f4f8f8; }.business-result small { color: var(--text-secondary); }.ask-message-card section { padding: 8px 0; border-top: 1px solid var(--border-weak); }.ask-message-card section p { font-size: 13px; }.ask-message-card section span { color: var(--text-secondary); font-size: 12px; }
</style>
