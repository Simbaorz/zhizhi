<script setup lang="ts">
const props = withDefaults(
  defineProps<{
  label: string;
  modelValue: string;
  placeholder?: string;
  type?: string;
  disabled?: boolean;
  readonly?: boolean;
  name?: string;
  autocomplete?: string;
  size?: "large" | "default" | "small";
}>(),
  {
    placeholder: "",
    type: "text",
    disabled: false,
    readonly: false,
    name: "",
    autocomplete: undefined,
    size: "default",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  focus: [event: FocusEvent];
}>();
</script>

<template>
  <label class="flex min-w-0 flex-col gap-1 text-xs font-medium text-secondary-text">
    <span>{{ label }}</span>
    <el-input
      :model-value="props.modelValue"
      :type="props.type"
      :disabled="props.disabled"
      :readonly="props.readonly"
      :name="props.name"
      :autocomplete="props.autocomplete"
      :placeholder="props.placeholder"
      :size="props.size"
      class="field-input"
      @focus="(event: FocusEvent) => emit('focus', event)"
      @update:model-value="(value: string | number) => emit('update:modelValue', String(value))"
    />
  </label>
</template>

<style scoped>
.field-input {
  width: 100%;
  --el-input-bg-color: var(--bg-panel);
  --el-input-border-color: var(--border-weak);
  --el-input-focus-border-color: var(--accent);
  --el-input-hover-border-color: color-mix(in srgb, var(--accent) 30%, var(--border-weak));
  --el-input-text-color: var(--text-primary);
  --el-input-placeholder-color: var(--text-tertiary);
}
</style>
