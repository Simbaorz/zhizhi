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
    placement?: "drawer" | "modal";
    size?: "default" | "wide" | "viewport";
  }>(),
  {
    subtitle: "",
    saving: false,
    submitDisabled: false,
    submitText: "保存",
    placement: "drawer",
    size: "default",
  },
);

const emit = defineEmits<{
  close: [];
  closed: [];
  submit: [];
}>();

const isModal = computed(() => props.placement === "modal");

const drawerSize = computed(() => {
  return props.size === "wide" ? "min(42rem, 92vw)" : "min(34rem, 92vw)";
});

const dialogWidth = computed(() => {
  if (props.size === "viewport") {
    return "78vw";
  }
  return props.size === "wide" ? "min(72rem, 92vw)" : "min(56rem, 92vw)";
});

const dialogClass = computed(() => {
  return props.size === "viewport" ? "app-form-dialog app-form-dialog--viewport" : "app-form-dialog";
});

function handleVisibleChange(visible: boolean): void {
  if (!visible) {
    emit("close");
  }
}
</script>

<template>
  <el-dialog
    v-if="isModal"
    :model-value="props.open"
    :width="dialogWidth"
    :class="dialogClass"
    append-to-body
    align-center
    lock-scroll
    :show-close="false"
    @closed="emit('closed')"
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

  <el-drawer
    v-else
    :model-value="props.open"
    :size="drawerSize"
    append-to-body
    direction="rtl"
    lock-scroll
    :show-close="false"
    class="app-form-drawer"
    modal-class="app-form-drawer-overlay"
    @closed="emit('closed')"
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
  </el-drawer>
</template>
