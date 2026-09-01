import { ref } from "vue";
import { defineStore } from "pinia";

export type NoticeTone = "info" | "success" | "warning" | "danger";

export interface Notice {
  id: number;
  tone: NoticeTone;
  title: string;
  body?: string;
  durationMs: number;
  createdAt: number;
}

export const useUiStore = defineStore("ui", () => {
  const notices = ref<Notice[]>([]);
  const mobileSidebarOpen = ref(false);
  const sidebarCollapsed = ref(readSidebarCollapsed());
  let nextId = 1;

  function readSidebarCollapsed(): boolean {
    if (typeof window === "undefined") {
      return false;
    }
    return window.localStorage.getItem("zhizhi-admin-sidebar-collapsed") === "true";
  }

  function noticeMessage(input: Pick<Notice, "title" | "body">): string {
    return (input.body || input.title).trim();
  }

  function pushNotice(input: Omit<Notice, "id" | "durationMs" | "createdAt"> & { durationMs?: number }): void {
    const message = noticeMessage(input);
    const duplicated = notices.value.some(
      (notice) =>
        notice.tone === input.tone &&
        (noticeMessage(notice) === message ||
          (notice.title === input.title && (notice.body ?? "") === (input.body ?? ""))),
    );
    if (duplicated) {
      return;
    }
    const id = nextId++;
    const durationMs =
      Number.isFinite(input.durationMs) && input.durationMs !== undefined && input.durationMs > 0
        ? input.durationMs
        : 3000;
    notices.value.push({ id, ...input, durationMs, createdAt: Date.now() });
    window.setTimeout(() => {
      notices.value = notices.value.filter((notice) => notice.id !== id);
    }, durationMs);
  }

  function dismissNotice(id: number): void {
    notices.value = notices.value.filter((notice) => notice.id !== id);
  }

  function toggleSidebarCollapsed(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value;
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        "zhizhi-admin-sidebar-collapsed",
        String(sidebarCollapsed.value),
      );
    }
  }

  return {
    notices,
    mobileSidebarOpen,
    sidebarCollapsed,
    pushNotice,
    dismissNotice,
    toggleSidebarCollapsed,
  };
});
