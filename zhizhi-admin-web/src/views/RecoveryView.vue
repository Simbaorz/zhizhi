<script setup lang="ts">
import { useRouter } from "vue-router";

import assistantIconUrl from "@/assets/zhizhi-logo.png";
import AppButton from "@/components/AppButton.vue";
import { useBootstrapStore } from "@/stores/bootstrap";

const router = useRouter();
const bootstrapStore = useBootstrapStore();

async function retry(): Promise<void> {
  try {
    await bootstrapStore.refresh();
    if (bootstrapStore.ready) {
      await router.replace("/login");
    } else if (bootstrapStore.state === "setup_required") {
      await router.replace("/setup");
    }
  } catch {
    // Keep the recovery page visible while the service is unavailable.
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-shell">
      <div class="login-brand">
        <div class="brand-lockup">
          <div class="brand-orb"><img class="brand-mascot" :src="assistantIconUrl" alt="致知" /></div>
          <div class="brand-title">致知</div>
          <div class="brand-subtitle">安装状态恢复</div>
        </div>
      </div>
      <div class="login-card-wrap">
        <section class="login-card recovery-card">
          <div>
            <p class="form-kicker">需要人工处理</p>
            <h2>安装状态不一致</h2>
            <p class="form-helper">系统检测到初始化记录或超级管理员账号异常。为避免覆盖现有数据，自动初始化已停止。</p>
          </div>
          <p class="recovery-copy">请检查数据库中的安装记录与超级管理员账号，或从可信备份恢复。修复后可重新检测。</p>
          <AppButton variant="primary" size="large" :disabled="bootstrapStore.loading" @click="retry">
            {{ bootstrapStore.loading ? "检测中..." : "重新检测" }}
          </AppButton>
        </section>
      </div>
    </section>
  </main>
</template>

<style scoped>
.recovery-card { gap: 1.5rem; }
.recovery-copy { margin: 0; border-left: 3px solid var(--warning); padding: 0.8rem 1rem; background: color-mix(in srgb, var(--warning) 8%, white); color: var(--text-secondary); line-height: 1.75; }
</style>
