<script setup lang="ts">
import { onBeforeUnmount, watch } from "vue";
import { ElMessage } from "element-plus";
import { storeToRefs } from "pinia";

import { useUiStore, type Notice, type NoticeTone } from "@/stores/ui";

type MessageHandler = {
  close: () => void;
};

const uiStore = useUiStore();
const { notices } = storeToRefs(uiStore);
const activeMessages = new Map<number, MessageHandler>();

function noticeText(notice: Notice): string {
  return notice.body || notice.title;
}

function elementMessageType(tone: NoticeTone): "info" | "success" | "warning" | "error" {
  if (tone === "danger") {
    return "error";
  }
  return tone;
}

function showNotice(notice: Notice): void {
  const handler = ElMessage({
    message: noticeText(notice),
    type: elementMessageType(notice.tone),
    duration: notice.durationMs,
    showClose: true,
    offset: 24,
    onClose: () => {
      activeMessages.delete(notice.id);
      uiStore.dismissNotice(notice.id);
    },
  });
  activeMessages.set(notice.id, handler);
}

function syncMessages(items: Notice[]): void {
  const activeIds = new Set(items.map((notice) => notice.id));
  for (const notice of items) {
    if (!activeMessages.has(notice.id)) {
      showNotice(notice);
    }
  }
  for (const [id, handler] of activeMessages.entries()) {
    if (!activeIds.has(id)) {
      activeMessages.delete(id);
      handler.close();
    }
  }
}

watch(notices, syncMessages, { immediate: true, deep: true });

onBeforeUnmount(() => {
  for (const handler of activeMessages.values()) {
    handler.close();
  }
  activeMessages.clear();
});
</script>

<template></template>
