import { computed } from "vue";
import { defineStore } from "pinia";

import { useAuthStore } from "@/stores/auth";

export const useNavigationStore = defineStore("navigation", () => {
  const authStore = useAuthStore();

  const items = computed(() => authStore.navigation);
  const defaultPath = computed(() => "/");

  return {
    items,
    defaultPath,
  };
});
