<script setup lang="ts">
import { computed, type Component } from "vue";
import {
  Checked as ShieldCheck,
  Clock,
  Postcard,
  User as UserRound,
} from "@element-plus/icons-vue";
import { storeToRefs } from "pinia";

import { useAuthStore } from "@/stores/auth";
import { formatDate } from "@/utils/format";

const authStore = useAuthStore();
const authRefs = storeToRefs(authStore);
const sessionIcons: Record<string, Component> = {
  user: UserRound,
  card: Postcard,
  shield: ShieldCheck,
  clock: Clock,
};

const sessionRows = computed(() => [
  { icon: "user", label: "用户名", value: authRefs.user.value?.username || "-" },
  { icon: "card", label: "显示名", value: authRefs.user.value?.display_name || "-" },
  {
    icon: "shield",
    label: "权限模式",
    value: authRefs.user.value?.is_super ? "超级管理员" : "普通后台账号",
  },
  {
    icon: "clock",
    label: "最近登录",
    value: authRefs.user.value?.last_login_time
      ? formatDate(authRefs.user.value.last_login_time)
      : "暂无记录",
  },
]);
</script>

<template>
  <div class="dashboard-page dashboard-simple">
    <article class="dashboard-panel session-panel">
      <div class="session-card">
        <div class="session-list">
          <div v-for="row in sessionRows" :key="row.label" class="session-row">
            <el-icon class="row-icon" aria-hidden="true">
              <component :is="sessionIcons[row.icon]" />
            </el-icon>
            <span class="session-label">{{ row.label }}</span>
            <strong>{{ row.value }}</strong>
          </div>
        </div>
      </div>
    </article>
  </div>
</template>
