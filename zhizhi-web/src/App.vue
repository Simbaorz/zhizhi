<script setup lang="ts">
import zhCn from "element-plus/es/locale/lang/zh-cn";
import { ElMessage, ElMessageBox } from "element-plus";
import { ChatDotRound, CircleCloseFilled, Edit, FolderRemove, Lock, Plus, RefreshLeft, Right, Service, SwitchButton, User } from "@element-plus/icons-vue";
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from "vue";

import assistantIconUrl from "@/assets/zhizhi-logo.png";
import ChatComposer from "@/components/ChatComposer.vue";
import MessageBubble from "@/components/MessageBubble.vue";
import { useChat } from "@/composables/useChat";
import { changePassword, createConversation, currentAccount, getConversation, listConversations, listScopes, login, logout, updateConversation, setUnauthorizedHandler } from "@/api/client";
import type { PortalAccount, PortalConversation, PortalScope } from "@/api/client";
import type { AgentSession, SlashTarget } from "@/types";
import { buildDisplayMessages } from "@/utils/messages";

const chat = useChat();
const { session, messages, targets, capabilities, imageSupportStatus, pendingAsk, runState,
  loading, loadingOlder, streaming, errorMessage, hasMoreMessages } = chat;
const account = ref<PortalAccount | null>(null);
const scopes = ref<PortalScope[]>([]);
const selectedScopeId = ref("");
const conversations = ref<PortalConversation[]>([]);
const conversationView = ref<"recent" | "archived">("recent");
const conversationViews = [{ label: "最近会话", value: "recent" }, { label: "已归档", value: "archived" }];
const selectedConversation = ref<PortalConversation | null>(null);
const moreConversations = ref(false);
const loadingConversations = ref(false);
let conversationListRequest = 0;
const restoring = ref(true);
const loginLoading = ref(false);
const loginError = ref("");
const username = ref("");
const password = ref("");
const passwordDialogOpen = ref(false);
const passwordSaving = ref(false);
const currentPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const canSubmitLogin = computed(() => Boolean(username.value.trim()) && Boolean(password.value) && !loginLoading.value);
const messageList = ref<HTMLElement | null>(null);
const displayMessages = computed(() => buildDisplayMessages(messages.value));
const conversationRunning = computed(() => streaming.value || ["pending", "running"].includes(runState.value ?? ""));
const activeScope = computed(() => scopes.value.find((item) => item.id === selectedConversation.value?.scope_id));
const scopeLabel = computed(() => activeScope.value
  ? `${activeScope.value.tenant_name} · ${activeScope.value.organization_path.join(' / ') || '租户范围'}`
  : "选择会话开始对话");

onMounted(async () => {
  setUnauthorizedHandler(() => { if (account.value) clearWorkspace(); });
  try {
    account.value = await currentAccount();
    await loadWorkspace();
  } catch {
    account.value = null;
  } finally {
    restoring.value = false;
  }
});
onBeforeUnmount(() => setUnauthorizedHandler(null));
watch(() => [messages.value.length, streaming.value, pendingAsk.value?.askId], () => scrollToBottom());

async function loadWorkspace(): Promise<void> {
  scopes.value = await listScopes();
  selectedScopeId.value = scopes.value[0]?.id ?? "";
  conversationView.value = "recent";
  await refreshConversations();
  const lastId = window.localStorage.getItem("zhizhi-web-last-conversation");
  if (lastId) {
    try {
      const last = conversations.value.find((item) => item.id === lastId) ?? await getConversation(lastId);
      if (!last.archived) await openConversation(last);
    } catch { window.localStorage.removeItem("zhizhi-web-last-conversation"); }
  }
}

async function submitLogin(): Promise<void> {
  if (!canSubmitLogin.value) return;
  loginLoading.value = true;
  loginError.value = "";
  try {
    account.value = await login(username.value.trim(), password.value);
    password.value = "";
    await loadWorkspace();
  } catch (error) {
    loginError.value = error instanceof Error ? error.message : "登录失败";
  } finally {
    loginLoading.value = false;
  }
}

async function signOut(): Promise<void> {
  try { await logout(); } catch { /* Clear local state even if the session expired. */ }
  clearWorkspace();
}

function clearWorkspace(): void {
  passwordDialogOpen.value = false;
  clearPasswordForm();
  account.value = null;
  conversationListRequest += 1;
  conversationView.value = "recent";
  scopes.value = [];
  conversations.value = [];
  moreConversations.value = false;
  loadingConversations.value = false;
  selectedConversation.value = null;
  window.localStorage.removeItem("zhizhi-web-last-conversation");
  chat.reset();
}

function clearPasswordForm(): void {
  currentPassword.value = "";
  newPassword.value = "";
  confirmPassword.value = "";
}

function handleAccountCommand(command: string): void {
  if (command === "password") passwordDialogOpen.value = true;
  if (command === "logout") void signOut();
}

async function submitPasswordChange(): Promise<void> {
  if (passwordSaving.value) return;
  if (!currentPassword.value || newPassword.value.length < 12 || newPassword.value.length > 256) {
    ElMessage.warning("请填写当前密码，新密码须为 12 至 256 位");
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    ElMessage.warning("两次输入的新密码不一致");
    return;
  }
  if (newPassword.value === currentPassword.value) {
    ElMessage.warning("新密码不能与当前密码相同");
    return;
  }
  passwordSaving.value = true;
  try {
    await changePassword(currentPassword.value, newPassword.value);
    passwordDialogOpen.value = false;
    clearPasswordForm();
    await signOut();
    ElMessage.success("密码已更新，请使用新密码重新登录");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "修改密码失败");
  } finally {
    passwordSaving.value = false;
  }
}

async function refreshConversations(): Promise<void> {
  const request = ++conversationListRequest;
  const archived = conversationView.value === "archived";
  loadingConversations.value = true;
  try {
    const page = await listConversations(0, archived);
    if (request !== conversationListRequest) return;
    conversations.value = page.items;
    moreConversations.value = page.has_more;
  } catch (error) {
    if (request === conversationListRequest) ElMessage.error(error instanceof Error ? error.message : "会话列表加载失败");
  } finally {
    if (request === conversationListRequest) loadingConversations.value = false;
  }
}

async function switchConversationView(): Promise<void> {
  conversations.value = [];
  moreConversations.value = false;
  await refreshConversations();
}

async function loadMoreConversations(): Promise<void> {
  if (!moreConversations.value || loadingConversations.value) return;
  const request = conversationListRequest;
  const archived = conversationView.value === "archived";
  loadingConversations.value = true;
  try {
    const page = await listConversations(conversations.value.length, archived);
    if (request !== conversationListRequest) return;
    conversations.value.push(...page.items);
    moreConversations.value = page.has_more;
  } finally {
    if (request === conversationListRequest) loadingConversations.value = false;
  }
}

function asSession(conversation: PortalConversation): AgentSession {
  const scope = scopes.value.find((item) => item.id === conversation.scope_id);
  if (!scope || !account.value) throw new Error("会话对应的租户或组织范围已失效");
  return { conversation_id: conversation.id };
}

async function openConversation(conversation: PortalConversation): Promise<void> {
  if (conversation.archived || streaming.value || loading.value) return;
  try {
    const nextSession = asSession(conversation);
    selectedConversation.value = conversation;
    selectedScopeId.value = conversation.scope_id;
    window.localStorage.setItem("zhizhi-web-last-conversation", conversation.id);
    await chat.bootstrap(nextSession);
    scrollToBottom();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "会话打开失败");
  }
}

async function startConversation(): Promise<void> {
  if (!selectedScopeId.value || streaming.value) return;
  try {
    const conversation = await createConversation(selectedScopeId.value);
    if (conversationView.value === "archived") {
      conversationView.value = "recent";
      await switchConversationView();
    } else conversations.value.unshift(conversation);
    await openConversation(conversation);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "新建会话失败");
  }
}

async function archiveConversation(conversation: PortalConversation): Promise<void> {
  if (conversationRunning.value) return;
  try {
    await ElMessageBox.confirm("归档后可在“已归档”中找到并恢复这个会话。", "归档会话", {
      confirmButtonText: "归档", cancelButtonText: "取消", type: "warning",
    });
  } catch { return; }
  try {
    await updateConversation(conversation.id, { archived: true });
    if (selectedConversation.value?.id === conversation.id) {
      selectedConversation.value = null;
      window.localStorage.removeItem("zhizhi-web-last-conversation");
      chat.reset();
    }
    await refreshConversations();
    ElMessage.success("会话已归档");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "归档失败");
  }
}

async function restoreConversation(conversation: PortalConversation): Promise<void> {
  if (conversationRunning.value) return;
  try {
    await updateConversation(conversation.id, { archived: false });
    conversationView.value = "recent";
    await switchConversationView();
    ElMessage.success("会话已恢复");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "恢复失败");
  }
}

async function renameConversation(conversation: PortalConversation): Promise<void> {
  if (streaming.value) return;
  let title: string;
  try {
    const result = await ElMessageBox.prompt("请输入新的会话名称", "重命名会话", {
      inputValue: conversation.title,
      confirmButtonText: "确认",
      cancelButtonText: "取消",
      inputValidator: (value) => {
        const name = String(value ?? "").trim();
        if (!name) return "会话名称不能为空";
        return name.length <= 128 || "会话名称不能超过 128 个字符";
      },
    });
    title = result.value.trim();
  } catch { return; }
  if (title === conversation.title) return;
  try {
    const updated = await updateConversation(conversation.id, { title });
    conversations.value = [updated, ...conversations.value.filter((item) => item.id !== updated.id)];
    if (selectedConversation.value?.id === updated.id) selectedConversation.value = updated;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "重命名失败");
  }
}

function formatRelativeTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "暂无时间";
  const elapsed = Math.max(0, Date.now() - date.getTime());
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (elapsed < minute) return "刚刚";
  if (elapsed < hour) return `${Math.floor(elapsed / minute)} 分钟前`;
  if (elapsed < day) return `${Math.floor(elapsed / hour)} 小时前`;
  if (elapsed < 7 * day) return `${Math.floor(elapsed / day)} 天前`;
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

async function send(content: string, files: File[], slashTarget: SlashTarget | null): Promise<void> {
  await chat.sendMessage(content, files, slashTarget);
  await refreshConversations();
  if (selectedConversation.value) {
    selectedConversation.value = conversations.value.find((item) => item.id === selectedConversation.value?.id) ?? null;
  }
}

function scrollToBottom(): void {
  void nextTick(() => {
    if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight;
  });
}
</script>

<template>
  <el-config-provider :locale="zhCn" size="default">
    <div v-if="restoring" class="portal-loading">正在恢复登录…</div>
    <main v-else-if="!account" class="portal-login-page">
      <aside class="portal-login-brand">
        <div class="portal-login-lockup">
          <span class="portal-brand-mark"><img :src="assistantIconUrl" alt="" class="portal-login-icon" /></span>
          <div><span class="portal-brand-eyebrow">格物致知</span><h1>致知助手</h1></div>
        </div>
        <p>在场景中提问，在知识中求证</p>
      </aside>
      <section class="portal-login-main">
        <el-card class="portal-login-card" shadow="never">
          <p class="portal-login-eyebrow">用户端</p>
          <h2>登录</h2>
          <p class="portal-login-description">登录后继续之前的对话。</p>
          <el-form class="portal-login-form" label-position="top" size="large" @submit.prevent="submitLogin">
            <el-form-item label="用户名" required>
              <el-input v-model="username" autocomplete="username" placeholder="请输入用户名" :prefix-icon="User" />
            </el-form-item>
            <el-form-item label="密码" required>
              <el-input v-model="password" type="password" show-password autocomplete="current-password"
                placeholder="请输入密码" :prefix-icon="Lock" />
            </el-form-item>
            <el-alert v-if="loginError" class="portal-login-error" :title="loginError" type="error" show-icon :closable="false" />
            <el-button class="portal-login-button" type="primary" native-type="submit" :icon="Right"
              :loading="loginLoading" :disabled="!canSubmitLogin">登录</el-button>
          </el-form>
        </el-card>
      </section>
    </main>
    <el-container v-else class="chat-shell portal-shell">
      <el-aside width="264px" class="portal-sidebar">
        <header class="portal-sidebar-head">
          <span class="portal-brand-mark"><img :src="assistantIconUrl" alt="" /></span>
          <div class="portal-sidebar-brand-copy">
            <span class="portal-brand-eyebrow">格物致知</span>
            <strong>致知助手</strong>
            <small>知识驱动行动</small>
          </div>
        </header>
        <div class="portal-create">
          <el-select v-if="scopes.length > 1" v-model="selectedScopeId" placeholder="选择租户与组织范围" :disabled="streaming" aria-label="租户与组织范围">
            <el-option v-for="scope in scopes" :key="scope.id" :value="scope.id"
              :label="`${scope.tenant_name} · ${scope.organization_path.join(' / ') || '租户范围'}`" />
          </el-select>
          <el-button type="primary" :icon="Plus" :disabled="!selectedScopeId || streaming" @click="startConversation">新建对话</el-button>
        </div>
        <div class="portal-list-title">
          <el-segmented v-model="conversationView" :options="conversationViews" @change="switchConversationView" />
          <el-tag type="info" effect="plain" round size="small">{{ conversations.length }} 条</el-tag>
        </div>
        <nav class="portal-conversation-list app-scrollbar" aria-label="会话记录">
          <div v-for="conversation in conversations" :key="conversation.id" :role="conversation.archived ? 'group' : 'button'"
            class="portal-conversation" :class="{ active: selectedConversation?.id === conversation.id, disabled: conversationRunning || conversation.archived }"
            :tabindex="conversationRunning || conversation.archived ? -1 : 0" :aria-disabled="conversationRunning || conversation.archived"
            @click="openConversation(conversation)" @keydown.enter.stop.prevent="openConversation(conversation)">
            <span class="portal-conversation-title">{{ conversation.title }}</span>
            <small :title="formatDateTime(conversation.updated_at)">{{ formatRelativeTime(conversation.updated_at) }}</small>
            <span class="portal-conversation-actions">
              <el-button class="portal-conversation-action" link :icon="Edit" title="重命名会话" aria-label="重命名会话"
                :disabled="conversationRunning" @click.stop="renameConversation(conversation)" />
              <el-button v-if="conversation.archived" class="portal-conversation-action" link :icon="RefreshLeft"
                title="恢复会话" aria-label="恢复会话" :disabled="conversationRunning" @click.stop="restoreConversation(conversation)" />
              <el-button v-else class="portal-conversation-action" link :icon="FolderRemove"
                title="归档会话" aria-label="归档会话" :disabled="conversationRunning" @click.stop="archiveConversation(conversation)" />
            </span>
          </div>
          <el-empty v-if="!conversations.length && !loadingConversations"
            :description="conversationView === 'archived' ? '暂无已归档会话' : '暂无会话'" :image-size="60" />
          <el-button v-if="moreConversations" text :loading="loadingConversations" @click="loadMoreConversations">加载更多</el-button>
        </nav>
        <footer class="portal-account">
          <el-avatar class="portal-account-avatar" :size="34">{{ account.display_name.slice(0, 1) }}</el-avatar>
          <div class="portal-account-copy"><strong>{{ account.display_name }}</strong><small>{{ account.username }}</small></div>
          <el-button class="portal-account-logout" circle :icon="SwitchButton" title="退出登录" aria-label="退出登录" @click="signOut" />
        </footer>
      </el-aside>
      <el-main class="chat-panel">
        <section class="chat-workspace">
          <el-card class="chat-content-card" shadow="never">
            <template #header>
              <header class="chat-header">
                <div class="chat-brand-lockup">
                  <img :src="assistantIconUrl" alt="致知助手" />
                  <div><h1>{{ selectedConversation?.title || "致知助手" }}</h1></div>
                </div>
                <div class="chat-toolbar">
                  <el-button v-if="conversationRunning || pendingAsk" class="workspace-menu-trigger stop-run" @click="chat.interrupt">
                    <span class="stop-run-glyph" aria-hidden="true" />停止输出
                  </el-button>
                  <el-dropdown trigger="click" @command="handleAccountCommand">
                    <button type="button" class="session-summary session-account-trigger" :title="session ? scopeLabel : account.username"
                      aria-label="账号设置">
                      <el-avatar class="session-avatar" :size="30">{{ account.display_name.slice(0, 1) }}</el-avatar>
                      <span><strong>{{ account.display_name }}</strong><small>{{ session ? scopeLabel : account.username }}</small></span>
                    </button>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="password" :icon="Lock">修改密码</el-dropdown-item>
                        <el-dropdown-item command="logout" :icon="SwitchButton" divided>退出登录</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </header>
            </template>
            <section ref="messageList" class="message-list app-scrollbar">
              <el-skeleton v-if="loading" class="message-loading" :rows="5" animated />
              <div v-else-if="!session" class="chat-empty-state">
                <el-icon class="chat-empty-icon"><ChatDotRound /></el-icon>
                <h2>开始新的对话</h2><p>{{ scopes.length ? '新建对话，或从左侧打开历史会话。' : '当前账号没有可用组织范围。' }}</p>
                <el-button type="primary" :disabled="!selectedScopeId" @click="startConversation">新建对话</el-button>
              </div>
              <div v-else-if="!displayMessages.length && !conversationRunning" class="chat-empty-state">
                <el-icon class="chat-empty-icon"><ChatDotRound /></el-icon>
                <h2>开始新的对话</h2><p>输入 / 选择场景，也可以直接发起普通对话。</p>
              </div>
              <template v-else>
                <div class="message-history-status">
                  <el-button v-if="hasMoreMessages" link type="primary" :loading="loadingOlder" @click="chat.loadOlderMessages">加载更早消息</el-button>
                  <span v-else-if="displayMessages.length">已经到最早的消息</span>
                </div>
                <MessageBubble v-for="message in displayMessages" :key="message.message_id" :message="message" :session="session" />
                <article v-if="conversationRunning && !pendingAsk" class="message-row message-row-running">
                  <el-avatar class="message-avatar" :size="34" shape="square"><el-icon :size="18"><Service /></el-icon></el-avatar>
                  <el-card class="assistant-running-card" shadow="never"><span>正在处理</span><span class="assistant-running-dots" aria-hidden="true"><i /><i /><i /></span></el-card>
                </article>
                <article v-else-if="runState === 'cancelled'" class="message-row message-row-running">
                  <el-avatar class="message-avatar message-avatar-warning" :size="34" shape="square"><el-icon><CircleCloseFilled /></el-icon></el-avatar>
                  <el-card class="system-message-card warning" shadow="never">用户已经主动打断</el-card>
                </article>
              </template>
            </section>
          </el-card>
          <div class="chat-composer-dock">
            <el-alert v-if="errorMessage" class="chat-error" type="error" show-icon :closable="true"
              :title="errorMessage" @close="errorMessage = ''" />
            <ChatComposer :disabled="conversationRunning || !session" :no-conversation="!session" :targets="targets" :pending-ask="pendingAsk"
              :capabilities="capabilities" :image-support-status="imageSupportStatus" @send="send"
              @answer-ask="(answers) => chat.submitAsk(answers, 'answered')"
              @dismiss-ask="(answers) => chat.submitAsk(answers, 'skipped')"
              @refresh-targets="chat.refreshCatalogs" />
          </div>
        </section>
      </el-main>
    </el-container>
    <el-dialog v-model="passwordDialogOpen" title="修改密码" width="420px" :close-on-click-modal="false"
      @closed="clearPasswordForm">
      <el-form label-position="top" @submit.prevent="submitPasswordChange">
        <el-form-item label="当前密码" required>
          <el-input v-model="currentPassword" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码" required>
          <el-input v-model="newPassword" type="password" show-password autocomplete="new-password" placeholder="12 至 256 位" />
        </el-form-item>
        <el-form-item label="确认新密码" required>
          <el-input v-model="confirmPassword" type="password" show-password autocomplete="new-password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="passwordSaving" @click="submitPasswordChange">保存并重新登录</el-button>
      </template>
    </el-dialog>
  </el-config-provider>
</template>
