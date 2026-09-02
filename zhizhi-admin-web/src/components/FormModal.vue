<script setup lang="ts">
import { computed } from "vue";
import { Close } from "@element-plus/icons-vue";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    subtitle?: string;
    saving?: boolean;
    submitDisabled?: boolean;
    submitText?: string;
    size?: "default" | "wide";
  }>(),
  {
    subtitle: "",
    saving: false,
    submitDisabled: false,
    submitText: "保存",
    size: "default",
  },
);

const emit = defineEmits<{
  close: [];
  submit: [];
}>();

const dialogWidth = computed(() => {
  return props.size === "wide" ? "min(72rem, 92vw)" : "min(48rem, 92vw)";
});

function handleVisibleChange(visible: boolean): void {
  if (!visible) {
    emit("close");
  }
}
</script>

<template>
  <el-dialog
    :model-value="props.open"
    :width="dialogWidth"
    :class="{ 'app-form-dialog': true, 'app-form-dialog--wide': props.size === 'wide' }"
    append-to-body
    align-center
    lock-scroll
    :show-close="false"
    @update:model-value="handleVisibleChange"
  >
    <template #header>
      <header class="app-form-surface-header">
        <div class="app-form-surface-title">
          <h2>{{ props.title }}</h2>
          <p v-if="props.subtitle">{{ props.subtitle }}</p>
        </div>
        <el-button :icon="Close" text circle aria-label="关闭" @click="emit('close')" />
      </header>
    </template>

    <form class="app-form-surface-body app-scrollbar" @submit.prevent="emit('submit')">
      <slot />
    </form>

    <template #footer>
      <footer class="app-form-surface-footer">
        <el-button :disabled="props.saving" @click="emit('close')">取消</el-button>
        <el-button type="primary" :loading="props.saving" :disabled="props.submitDisabled" @click="emit('submit')">
          {{ props.submitText }}
        </el-button>
      </footer>
    </template>
  </el-dialog>
</template>
