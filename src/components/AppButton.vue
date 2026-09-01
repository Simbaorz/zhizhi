<script setup lang="ts">
import { computed } from "vue";
import type { ButtonProps } from "element-plus";

const props = withDefaults(
  defineProps<{
    variant?: "primary" | "secondary" | "danger" | "ghost";
    disabled?: boolean;
    type?: "button" | "submit";
    size?: "large" | "default" | "small";
  }>(),
  {
    variant: "secondary",
    disabled: false,
    type: "button",
    size: "default",
  },
);

const elementType = computed<ButtonProps["type"]>(() => {
  if (props.variant === "primary") {
    return "primary";
  }
  if (props.variant === "danger") {
    return "danger";
  }
  return "";
});
</script>

<template>
  <el-button
    :type="elementType"
    :native-type="props.type"
    :size="props.size"
    :disabled="props.disabled"
    :plain="props.variant === 'secondary'"
    :text="props.variant === 'ghost'"
    class="app-button"
    :class="`app-button--${props.variant}`"
  >
    <slot />
  </el-button>
</template>

<style scoped>
.app-button {
  font-weight: 700;
  letter-spacing: 0;
}

.app-button--primary {
  --el-button-bg-color: var(--accent);
  --el-button-border-color: var(--accent);
  --el-button-hover-bg-color: var(--accent-strong);
  --el-button-hover-border-color: var(--accent-strong);
  --el-button-active-bg-color: var(--accent-strong);
  --el-button-active-border-color: var(--accent-strong);
}

.app-button--secondary {
  --el-button-bg-color: var(--bg-panel-strong);
  --el-button-border-color: var(--border-strong);
  --el-button-text-color: var(--text-primary);
  --el-button-hover-bg-color: var(--bg-muted);
  --el-button-hover-border-color: color-mix(in srgb, var(--accent) 32%, var(--border-strong));
  --el-button-hover-text-color: var(--accent);
}

.app-button--ghost {
  --el-button-text-color: var(--text-secondary);
  --el-button-hover-bg-color: var(--bg-muted);
  --el-button-hover-text-color: var(--text-primary);
}

.app-button--danger {
  --el-color-danger: var(--danger);
}
</style>
