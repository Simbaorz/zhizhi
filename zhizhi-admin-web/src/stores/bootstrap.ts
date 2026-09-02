import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { getBootstrapStatus, initializeBootstrap } from "@/api/admin";
import { ApiError } from "@/api/http";
import type { BootstrapState } from "@/types/bootstrap";

export const useBootstrapStore = defineStore("bootstrap", () => {
  const state = ref<BootstrapState | null>(null);
  const bootstrapEnabled = ref(false);
  const checked = ref(false);
  const loading = ref(false);
  const errorMessage = ref("");

  const ready = computed(() => state.value === "ready");

  async function refresh(): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    try {
      const status = await getBootstrapStatus();
      state.value = status.state;
      bootstrapEnabled.value = status.bootstrap_enabled;
      checked.value = true;
    } catch (error) {
      state.value = null;
      bootstrapEnabled.value = false;
      checked.value = true;
      errorMessage.value =
        error instanceof ApiError ? error.message : "无法读取系统初始化状态。";
      throw error;
    } finally {
      loading.value = false;
    }
  }

  async function initialize(payload: {
    bootstrapToken: string;
    username: string;
    displayName: string;
    password: string;
  }): Promise<void> {
    loading.value = true;
    errorMessage.value = "";
    try {
      const status = await initializeBootstrap(payload);
      state.value = status.state;
      bootstrapEnabled.value = status.bootstrap_enabled;
      checked.value = true;
    } catch (error) {
      errorMessage.value = error instanceof ApiError ? error.message : "系统初始化失败。";
      throw error;
    } finally {
      loading.value = false;
    }
  }

  return {
    state,
    bootstrapEnabled,
    checked,
    loading,
    errorMessage,
    ready,
    refresh,
    initialize,
  };
});
