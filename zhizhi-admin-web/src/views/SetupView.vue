<script setup lang="ts">
import { InfoFilled, Lock, Setting } from "@element-plus/icons-vue";
import { computed, reactive } from "vue";
import { useRouter } from "vue-router";

import assistantIconUrl from "@/assets/zhizhi-logo.png";
import AppButton from "@/components/AppButton.vue";
import { useBootstrapStore } from "@/stores/bootstrap";
import { useUiStore } from "@/stores/ui";

const router = useRouter();
const bootstrapStore = useBootstrapStore();
const uiStore = useUiStore();
const form = reactive({
  bootstrapToken: "",
  username: "admin",
  displayName: "超级管理员",
  password: "",
  confirmPassword: "",
});

const formReady = computed(
  () =>
    bootstrapStore.bootstrapEnabled
    && form.bootstrapToken.trim() !== ""
    && form.username.trim() !== ""
    && form.displayName.trim() !== ""
    && form.password.length >= 12
    && form.password === form.confirmPassword,
);
const activeStep = computed(() => (bootstrapStore.bootstrapEnabled ? 1 : 0));
const passwordStrength = computed(() => {
  if (!form.password) return 0;
  let score = form.password.length >= 8 ? 1 : 0;
  if (form.password.length >= 12) score += 1;
  if (
    /[a-z]/.test(form.password)
    && /[A-Z]/.test(form.password)
    && /(?:\d|[^A-Za-z0-9])/.test(form.password)
  ) {
    score += 1;
  }
  return score;
});
const passwordStrengthLabel = computed(() => ["", "较弱", "中等", "较强"][passwordStrength.value]);
const passwordStrengthPercentage = computed(() => Math.round((passwordStrength.value / 3) * 100));

async function retryStatus(): Promise<void> {
  try {
    await bootstrapStore.refresh();
    if (bootstrapStore.ready) {
      await router.replace("/login");
    } else if (bootstrapStore.state === "recovery_required") {
      await router.replace("/recovery");
    }
  } catch {
    // The store exposes the user-facing error on this page.
  }
}

async function submit(): Promise<void> {
  if (!formReady.value) return;
  try {
    await bootstrapStore.initialize({
      bootstrapToken: form.bootstrapToken.trim(),
      username: form.username.trim(),
      displayName: form.displayName.trim(),
      password: form.password,
    });
    uiStore.pushNotice({ tone: "success", title: "初始化完成，请登录管理后台。" });
    await router.replace("/login");
  } catch {
    // The store exposes the user-facing error on this page.
  }
}
</script>

<template>
  <main class="setup-page">
    <header class="setup-header">
      <div class="setup-brand">
        <img :src="assistantIconUrl" alt="" />
        <strong>致知</strong>
      </div>
      <div class="setup-header-status">
        <el-icon><Setting /></el-icon>
        <span>系统初始化</span>
      </div>
    </header>

    <div class="setup-main">
      <el-steps class="setup-steps" :active="activeStep" finish-status="success" align-center>
        <el-step title="环境检查" />
        <el-step title="管理员账号" />
        <el-step title="完成" />
      </el-steps>

      <form class="setup-surface" @submit.prevent="submit">
        <header class="setup-intro">
          <p>首次运行</p>
          <h1>初始化致知</h1>
          <span>创建首位超级管理员，完成后即可进入管理后台。</span>
        </header>

        <div v-if="bootstrapStore.errorMessage" class="setup-message danger" role="alert">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ bootstrapStore.errorMessage }}</span>
          <button type="button" @click="retryStatus">重新检测</button>
        </div>
        <div v-else class="setup-message info" :class="{ pending: !bootstrapStore.bootstrapEnabled }">
          <el-icon><InfoFilled /></el-icon>
          <span>请先在根目录 <code>.env</code> 中配置 <code>ADMIN_BOOTSTRAP_TOKEN</code>，并重启 Admin API。</span>
          <button v-if="!bootstrapStore.bootstrapEnabled" type="button" @click="retryStatus">重新检测</button>
        </div>

        <div class="setup-form">
          <label class="setup-field">
            <span>初始化令牌</span>
            <el-input
              v-model="form.bootstrapToken"
              type="password"
              autocomplete="off"
              placeholder="请输入初始化令牌"
              size="large"
              show-password
            />
          </label>

          <div class="setup-grid">
            <label class="setup-field">
              <span>用户名</span>
              <el-input v-model="form.username" autocomplete="username" size="large" />
            </label>
            <label class="setup-field">
              <span>显示名称</span>
              <el-input v-model="form.displayName" autocomplete="name" size="large" />
            </label>
          </div>

          <label class="setup-field">
            <span>密码</span>
            <el-input
              v-model="form.password"
              type="password"
              autocomplete="new-password"
              placeholder="请输入密码"
              size="large"
              show-password
            />
            <div class="setup-password-meta">
              <small>至少 12 个字符</small>
              <div class="setup-strength" aria-live="polite">
                <span>{{ passwordStrengthLabel ? `密码强度：${passwordStrengthLabel}` : "密码强度" }}</span>
                <el-progress :percentage="passwordStrengthPercentage" :show-text="false" :stroke-width="5" />
              </div>
            </div>
          </label>

          <label class="setup-field">
            <span>确认密码</span>
            <el-input
              v-model="form.confirmPassword"
              type="password"
              autocomplete="new-password"
              placeholder="请再次输入密码"
              size="large"
              show-password
            />
          </label>
        </div>

        <footer class="setup-actions">
          <AppButton
            class="setup-submit"
            variant="primary"
            type="submit"
            size="large"
            :disabled="!formReady || bootstrapStore.loading"
          >
            {{ bootstrapStore.loading ? "正在创建..." : "创建超级管理员" }}
          </AppButton>
          <p><el-icon><Lock /></el-icon><span>初始化操作仅可执行一次</span></p>
        </footer>
      </form>
    </div>
  </main>
</template>

<style scoped>
.setup-page {
  min-height: 100vh;
  background: #f6f6fb;
  color: var(--text-primary);
}

.setup-header {
  display: flex;
  height: 72px;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(221, 221, 234, 0.9);
  background: rgba(255, 255, 255, 0.96);
  padding: 0 clamp(24px, 4vw, 64px);
}

.setup-brand,
.setup-header-status,
.setup-actions p,
.setup-message,
.setup-password-meta,
.setup-strength {
  display: flex;
  align-items: center;
}

.setup-brand {
  gap: 10px;
}

.setup-brand img {
  width: 38px;
  height: 38px;
  object-fit: contain;
}

.setup-brand strong {
  font-size: 21px;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.setup-header-status {
  gap: 8px;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 700;
}

.setup-header-status .el-icon {
  color: var(--accent);
}

.setup-main {
  width: min(100%, 930px);
  margin: 0 auto;
  padding: 38px 24px 28px;
}

.setup-steps {
  width: min(100%, 720px);
  margin: 0 auto 18px;
}

.setup-steps :deep(.el-step__title) {
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 700;
}

.setup-steps :deep(.el-step__title.is-process),
.setup-steps :deep(.el-step__head.is-process),
.setup-steps :deep(.el-step__title.is-success),
.setup-steps :deep(.el-step__head.is-success) {
  color: var(--accent);
  border-color: var(--accent);
}

.setup-steps :deep(.el-step__line) {
  background: var(--border-weak);
}

.setup-steps :deep(.el-step__line-inner) {
  border-color: var(--accent);
}

.setup-surface {
  overflow: hidden;
  border: 1px solid rgba(205, 205, 222, 0.88);
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 18px 50px rgba(36, 33, 62, 0.07);
  padding: 38px 44px 30px;
}

.setup-intro p {
  margin: 0 0 8px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.setup-intro h1 {
  margin: 0;
  font-size: clamp(28px, 3vw, 34px);
  font-weight: 800;
  letter-spacing: -0.035em;
  line-height: 1.25;
}

.setup-intro > span {
  display: block;
  margin-top: 9px;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.65;
}

.setup-message {
  min-height: 58px;
  margin-top: 26px;
  gap: 11px;
  border: 1px solid rgba(91, 91, 214, 0.28);
  border-radius: 11px;
  background: rgba(91, 91, 214, 0.065);
  padding: 12px 15px;
  color: #39368b;
  font-size: 13px;
  line-height: 1.55;
}

.setup-message > .el-icon {
  flex: 0 0 auto;
  color: var(--accent);
  font-size: 18px;
}

.setup-message > span {
  min-width: 0;
  flex: 1 1 auto;
}

.setup-message code {
  font-family: var(--font-mono);
  font-size: 0.94em;
  font-weight: 700;
}

.setup-message.pending {
  border-color: rgba(181, 124, 18, 0.3);
  background: rgba(181, 124, 18, 0.07);
  color: #77500a;
}

.setup-message.pending > .el-icon {
  color: var(--warning);
}

.setup-message.danger {
  border-color: rgba(194, 65, 58, 0.28);
  background: var(--danger-soft);
  color: var(--danger);
}

.setup-message.danger > .el-icon {
  color: var(--danger);
}

.setup-message button {
  flex: 0 0 auto;
  border: 0;
  background: transparent;
  padding: 6px 2px;
  color: inherit;
  font-size: 13px;
  font-weight: 800;
}

.setup-form {
  display: grid;
  gap: 22px;
  margin-top: 28px;
}

.setup-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.setup-field {
  display: grid;
  min-width: 0;
  gap: 8px;
}

.setup-field > span {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 750;
}

.setup-field :deep(.el-input__wrapper) {
  min-height: 48px;
  border-radius: 10px;
  background: #fbfbfe;
  box-shadow: 0 0 0 1px var(--border-weak) inset;
  transition: background-color 160ms ease, box-shadow 160ms ease;
}

.setup-field :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(91, 91, 214, 0.42) inset;
}

.setup-field :deep(.el-input__wrapper.is-focus) {
  background: #ffffff;
  box-shadow:
    0 0 0 1px var(--accent) inset,
    0 0 0 4px rgba(91, 91, 214, 0.1);
}

.setup-field :deep(.el-input__inner) {
  color: var(--text-primary);
  font-size: 14px;
}

.setup-password-meta {
  min-height: 18px;
  justify-content: space-between;
  gap: 16px;
}

.setup-password-meta small,
.setup-strength > span {
  color: var(--text-tertiary);
  font-size: 12px;
}

.setup-strength {
  width: min(210px, 48%);
  justify-content: flex-end;
  gap: 10px;
}

.setup-strength > span {
  flex: 0 0 auto;
}

.setup-strength .el-progress {
  width: 96px;
}

.setup-strength :deep(.el-progress-bar__outer) {
  background: var(--bg-muted);
}

.setup-strength :deep(.el-progress-bar__inner) {
  background: var(--accent);
}

.setup-actions {
  margin-top: 28px;
}

.setup-submit {
  width: 100%;
  height: 50px;
  border-radius: 11px;
  background: var(--accent);
  color: #ffffff;
  font-size: 15px;
  font-weight: 800;
  box-shadow: 0 12px 24px rgba(91, 91, 214, 0.2);
  transition: background-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.setup-submit:hover:not(:disabled) {
  background: var(--accent-strong);
  box-shadow: 0 16px 28px rgba(91, 91, 214, 0.24);
  transform: translateY(-1px);
}

.setup-actions p {
  justify-content: center;
  gap: 7px;
  margin: 16px 0 0;
  color: var(--text-tertiary);
  font-size: 12px;
}

.setup-actions p .el-icon {
  font-size: 14px;
}

@media (max-width: 720px) {
  .setup-header {
    height: 64px;
    padding: 0 20px;
  }

  .setup-brand img {
    width: 34px;
    height: 34px;
  }

  .setup-brand strong {
    font-size: 19px;
  }

  .setup-main {
    padding: 28px 16px 36px;
  }

  .setup-steps {
    margin-bottom: 24px;
  }

  .setup-steps :deep(.el-step__title) {
    font-size: 12px;
  }

  .setup-surface {
    border-radius: 14px;
    padding: 28px 22px 24px;
  }

  .setup-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .setup-header-status span {
    display: none;
  }

  .setup-main {
    padding-inline: 12px;
  }

  .setup-surface {
    padding-inline: 18px;
  }

  .setup-message {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .setup-message button {
    margin-left: 29px;
  }

  .setup-password-meta {
    align-items: flex-start;
    flex-direction: column;
    gap: 7px;
  }

  .setup-strength {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
