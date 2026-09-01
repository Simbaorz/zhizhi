<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import { useUiStore, type NoticeTone } from "@/stores/ui";

defineOptions({
  inheritAttrs: false,
});

const props = withDefaults(
  defineProps<{
    tone?: NoticeTone;
    title: string;
    body?: string;
  }>(),
  {
    tone: "info",
    body: "",
  },
);

const uiStore = useUiStore();
const lastNoticeKey = ref("");
const noticeKey = computed(() => `${props.tone}|${props.title}|${props.body}`);

function forwardNotice(): void {
  if (!props.title && !props.body) {
    return;
  }
  if (noticeKey.value === lastNoticeKey.value) {
    return;
  }
  lastNoticeKey.value = noticeKey.value;
  uiStore.pushNotice({
    tone: props.tone,
    title: props.title,
    body: props.body,
  });
}

onMounted(forwardNotice);
watch(noticeKey, forwardNotice);
</script>

<template>
  <span class="status-banner-sentinel" aria-hidden="true" />
</template>

<style scoped>
.status-banner-sentinel {
  display: none;
}
</style>
