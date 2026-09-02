<script setup lang="ts">
import { MdEditor, MdPreview } from "md-editor-v3";
import "md-editor-v3/lib/style.css";

defineProps<{
  modelValue: string;
  readonly?: boolean;
}>();

defineEmits<{
  "update:modelValue": [value: string];
}>();

type MarkdownToolbars = NonNullable<InstanceType<typeof MdEditor>["$props"]["toolbars"]>;

const toolbars: MarkdownToolbars = [
  "bold",
  "italic",
  "strikeThrough",
  "-",
  "title",
  "quote",
  "unorderedList",
  "orderedList",
  "task",
  "-",
  "codeRow",
  "code",
  "link",
  "table",
  "-",
  "preview",
  "previewOnly",
  "fullscreen",
];
</script>

<template>
  <MdPreview
    v-if="readonly"
    class="markdown-editor markdown-preview-only"
    :model-value="modelValue"
    :theme="'light'"
    :preview-theme="'github'"
    :code-theme="'github'"
    :language="'zh-CN'"
  />
  <MdEditor
    v-else
    class="markdown-editor"
    :model-value="modelValue"
    :read-only="readonly"
    :theme="'light'"
    :preview-theme="'github'"
    :code-theme="'github'"
    :language="'zh-CN'"
    :toolbars="toolbars"
    :preview="false"
    :footers="[]"
    :no-upload-img="true"
    :no-prettier="true"
    :show-toolbar-name="false"
    @update:model-value="$emit('update:modelValue', $event)"
  />
</template>
