<script setup lang="ts">
import zhCn from "element-plus/es/locale/lang/zh-cn";
import { ElMessageBox } from "element-plus";
import {
  ChatDotRound,
  CircleCloseFilled,
  Connection,
  Loading,
  Refresh,
  Service,
  SwitchButton,
} from "@element-plus/icons-vue";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import assistantIconUrl from "@/assets/zhizhi-logo.png";
import ChatComposer from "@/components/ChatComposer.vue";
import MessageBubble from "@/components/MessageBubble.vue";
import SessionDialog from "@/components/SessionDialog.vue";
import { useChat } from "@/composables/useChat";
import type { AgentSession, SlashTarget } from "@/types";
import { buildDisplayMessages } from "@/utils/messages";
import {
  clearTemporarySession,
  createDefaultSession,
  loadTemporarySession,
  saveTemporarySession,
} from "@/utils/session";

const chat = useChat();
const {
  session,
  messages,
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
} = chat;
const sessionDialogOpen = ref(false);
const sessionDraft = ref<AgentSession>(createDefaultSession());
const messageList = ref<HTMLElement | null>(null);
const displayMessages = computed(() => buildDisplayMessages(messages.value));
const sessionScope = computed(() => {
  const value = session.value;
  if (!value) return "尚未创建";
  return value.active_organization_unit_id
    ? `${value.tenant_id} · ${value.active_organization_unit_id}`
    : `${value.tenant_id} · 租户级`;
});
const sessionInitial = computed(() => session.value?.principal_id.trim().slice(0, 1) || "知");
const conversationRunning = computed(
  () => streaming.value || ["pending", "running"].includes(runState.value ?? ""),
);

onMounted(async () => {
  window.addEventListener("pagehide", chat.interruptKeepalive);
  window.addEventListener("beforeunload", chat.interruptKeepalive);
  const cached = loadTemporarySession();
  if (!cached) {
    sessionDialogOpen.value = true;
    return;
  }
  sessionDraft.value = cached;
  await chat.bootstrap(cached);
  scrollToBottom();
});

onBeforeUnmount(() => {
  window.removeEventListener("pagehide", chat.interruptKeepalive);
  window.removeEventListener("beforeunload", chat.interruptKeepalive);
});

watch(
  () => [messages.value.length, streaming.value, pendingAsk.value?.askId],
  () => scrollToBottom(),
);

async function createSession(value: AgentSession): Promise<void> {
  saveTemporarySession(value);
  sessionDraft.value = value;
  sessionDialogOpen.value = false;
  await chat.bootstrap(value);
  scrollToBottom();
}

async function requestNewSession(): Promise<void> {
  if (messages.value.length || conversationRunning.value || pendingAsk.value) {
    try {
      await ElMessageBox.confirm(
        "当前临时会话不会出现在会话列表中。重新创建后，本页将不再保留当前消息。",
        "重新创建临时会话",
        {
          confirmButtonText: "重新创建",
          cancelButtonText: "取消",
          type: "warning",
        },
      );
    } catch {
      return;
    }
  }
  if (conversationRunning.value || pendingAsk.value) await chat.interrupt();
  clearTemporarySession();
  chat.reset();
  sessionDraft.value = createDefaultSession();
  sessionDialogOpen.value = true;
}

async function send(content: string, files: File[], slashTarget: SlashTarget | null): Promise<void> {
  await chat.sendMessage(content, files, slashTarget);
}

function scrollToBottom(): void {
  void nextTick(() => {
    const element = messageList.value;
    if (element) element.scrollTop = element.scrollHeight;
  });
}
</script>

<template>
  <el-config-provider :locale="zhCn" size="default">
    <el-container class="chat-shell">
      <el-main class="chat-panel">
        <section class="chat-workspace">
          <el-card class="chat-content-card" shadow="never">
            <template #header>
              <header class="chat-header">
                <div class="chat-brand-lockup">
                  <img :src="assistantIconUrl" alt="致知助手" />
                  <div>
                    <p class="chat-kicker">
                      <el-icon><Connection /></el-icon>
                      企业知识问答工作台
                    </p>
                    <h1>{{ session?.conversation_id || "致知助手" }}</h1>
                  </div>
                </div>

                <div class="chat-toolbar">
                  <el-button
                    v-if="conversationRunning || pendingAsk"
                    class="workspace-menu-trigger stop-run"
                    @click="chat.interrupt"
                  >
                    <span class="stop-run-glyph" aria-hidden="true" />
                    停止输出
                  </el-button>
                  <div v-if="session" class="session-summary" :title="`${session.principal_id} · ${sessionScope}`">
                    <el-avatar class="session-avatar" :size="30">{{ sessionInitial }}</el-avatar>
                    <span>
                      <strong>{{ session.principal_id }}</strong>
                      <small>{{ sessionScope }}</small>
                    </span>
                  </div>
                  <el-button class="workspace-menu-trigger" :icon="Refresh" @click="requestNewSession">
                    重新创建
                  </el-button>
                </div>
              </header>
            </template>

            <section ref="messageList" class="message-list app-scrollbar">
              <el-skeleton v-if="loading" class="message-loading" :rows="5" animated />
              <div v-else-if="!session" class="chat-empty-state">
                <el-icon class="chat-empty-icon"><Connection /></el-icon>
                <h2>先创建一个临时会话</h2>
                <p>填写租户、组织单元与调用方身份后即可开始对话。</p>
                <el-button type="primary" @click="sessionDialogOpen = true">创建临时会话</el-button>
              </div>
              <div
                v-else-if="!displayMessages.length && !conversationRunning"
                class="chat-empty-state"
              >
                <el-icon class="chat-empty-icon"><ChatDotRound /></el-icon>
                <h2>开始新的对话</h2>
                <p>输入 / 选择技能或场景，也可以直接发起普通对话。</p>
              </div>
              <template v-else>
                <div class="message-history-status">
                  <el-button
                    v-if="hasMoreMessages"
                    link
                    type="primary"
                    :loading="loadingOlder"
                    @click="chat.loadOlderMessages"
                  >
                    加载更早消息
                  </el-button>
                  <span v-else-if="displayMessages.length">已经到最早的消息</span>
                </div>
                <MessageBubble
                  v-for="message in displayMessages"
                  :key="message.message_id"
                  :message="message"
                  :session="session"
                />
                <article v-if="conversationRunning && !pendingAsk" class="message-row message-row-running">
                  <el-avatar class="message-avatar" :size="34" shape="square">
                    <el-icon :size="18"><Service /></el-icon>
                  </el-avatar>
                  <el-card class="assistant-running-card" shadow="never">
                    <span>正在处理</span>
                    <span class="assistant-running-dots" aria-hidden="true"><i /><i /><i /></span>
                  </el-card>
                </article>
                <article v-else-if="runState === 'cancelled'" class="message-row message-row-running">
                  <el-avatar class="message-avatar message-avatar-warning" :size="34" shape="square">
                    <el-icon :size="18"><CircleCloseFilled /></el-icon>
                  </el-avatar>
                  <el-card class="system-message-card warning" shadow="never">用户已经主动打断</el-card>
                </article>
              </template>
            </section>
          </el-card>

          <div class="chat-composer-dock">
            <el-alert
              v-if="errorMessage"
              class="chat-error"
              type="error"
              show-icon
              :closable="true"
              :title="errorMessage"
              @close="errorMessage = ''"
            />
            <ChatComposer
              :disabled="conversationRunning || !session"
              :targets="targets"
              :pending-ask="pendingAsk"
              :capabilities="capabilities"
              :image-support-status="imageSupportStatus"
              @send="send"
              @answer-ask="(answers) => chat.submitAsk(answers, 'answered')"
              @dismiss-ask="(answers) => chat.submitAsk(answers, 'skipped')"
              @refresh-targets="chat.refreshCatalogs"
            />
          </div>
        </section>
      </el-main>

      <SessionDialog
        v-model="sessionDialogOpen"
        :initial-value="sessionDraft"
        @confirm="createSession"
      />
    </el-container>
  </el-config-provider>
</template>
