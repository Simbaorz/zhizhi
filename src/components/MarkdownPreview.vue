<script setup lang="ts">
import { MdPreview } from "md-editor-v3";
import "md-editor-v3/lib/preview.css";

import { sanitizeMarkdownHtml, sanitizeMermaidSvg } from "@/utils/markdownSanitizer";

defineProps<{ modelValue: string }>();
</script>

<template>
  <MdPreview
    class="markdown-editor markdown-preview-only"
    :model-value="modelValue"
    theme="light"
    preview-theme="github"
    code-theme="github"
    language="zh-CN"
    :sanitize="sanitizeMarkdownHtml"
    :sanitize-mermaid="sanitizeMermaidSvg"
  />
</template>
