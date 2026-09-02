<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";

import assistantIconUrl from "@/assets/zhizhi-logo.png";
import AppButton from "@/components/AppButton.vue";
import { useAuthStore } from "@/stores/auth";
import { useNavigationStore } from "@/stores/navigation";
import { useUiStore } from "@/stores/ui";

const router = useRouter();
const authStore = useAuthStore();
const navigationStore = useNavigationStore();
const uiStore = useUiStore();

const username = ref("admin");
const password = ref("");
const canSubmit = computed(() => username.value.trim() !== "" && password.value.trim() !== "");

watch(
  () => authStore.errorMessage,
  (message) => {
    if (message) {
      uiStore.pushNotice({ tone: "danger", title: message });
    }
  },
  { immediate: true },
);

async function submit(): Promise<void> {
  try {
    await authStore.login(username.value.trim(), password.value);
    await router.replace(navigationStore.defaultPath);
  } catch {
    // The store already exposes the user-facing login error.
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-shell">
      <div class="login-brand">
        <div class="brand-lockup">
          <div class="brand-orb">
            <img class="brand-mascot" :src="assistantIconUrl" alt="致知" />
          </div>
          <div class="brand-title">致知</div>
          <div class="brand-subtitle">管理后台</div>
        </div>
      </div>

      <div class="login-card-wrap">
        <form class="login-card" @submit.prevent="submit">
          <div>
            <p class="form-kicker">管理后台</p>
            <h2>登录</h2>
            <p class="form-helper">请输入管理员账号继续。</p>
          </div>

          <label class="login-field">
            <span>用户名</span>
            <el-input
              v-model="username"
              autocomplete="username"
              placeholder="请输入用户名"
              type="text"
              size="large"
            />
          </label>

          <label class="login-field">
            <span>密码</span>
            <el-input
              v-model="password"
              type="password"
              autocomplete="current-password"
              placeholder="请输入密码"
              size="large"
              show-password
            />
          </label>

          <AppButton class="login-submit" variant="primary" type="submit" size="large" :disabled="!canSubmit || authStore.loading">
            {{ authStore.loading ? "登录中..." : "登录" }}
          </AppButton>
        </form>
      </div>
    </section>
  </main>
</template>
