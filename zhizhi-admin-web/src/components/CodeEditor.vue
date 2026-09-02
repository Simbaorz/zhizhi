<script setup lang="ts">
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { sql } from "@codemirror/lang-sql";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorState, type Extension } from "@codemirror/state";
import { EditorView, keymap, lineNumbers, type ViewUpdate } from "@codemirror/view";
import { tags } from "@lezer/highlight";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{
  modelValue: string;
  filename?: string;
  readonly?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const host = ref<HTMLElement | null>(null);
let view: EditorView | null = null;
let syncingFromParent = false;

const languageExtension = computed<Extension>(() => {
  const name = (props.filename || "").toLowerCase();
  if (name.endsWith(".json")) return json();
  if (name.endsWith(".sql")) return sql();
  return markdown();
});

const editorTheme = EditorView.theme(
  {
    "&": {
      height: "100%",
      backgroundColor: "var(--code-editor-bg, #1f242a)",
      color: "var(--code-editor-color, #d8dee9)",
      fontSize: "var(--code-editor-font-size, 13px)",
    },
    ".cm-scroller": {
      overflow: "auto",
      fontFamily:
        "var(--code-editor-font-family, 'SFMono-Regular', 'JetBrains Mono', 'Cascadia Code', Menlo, Consolas, monospace)",
      lineHeight: "var(--code-editor-line-height, 1.65)",
      padding: "var(--code-editor-scroller-padding, 0)",
    },
    ".cm-content": {
      minHeight: "100%",
      padding: "var(--code-editor-content-padding, 16px 18px)",
      caretColor: "var(--code-editor-caret-color, #f8f8f2)",
    },
    ".cm-gutters": {
      backgroundColor: "var(--code-editor-gutter-bg, #181d22)",
      borderRight: "1px solid var(--code-editor-gutter-border, rgba(255, 255, 255, 0.08))",
      color: "var(--code-editor-gutter-color, #697782)",
    },
    ".cm-activeLineGutter": {
      backgroundColor: "var(--code-editor-active-gutter-bg, rgba(255, 255, 255, 0.06))",
      color: "var(--code-editor-active-gutter-color, #a7b3bd)",
    },
    ".cm-activeLine": {
      backgroundColor: "var(--code-editor-active-line-bg, rgba(255, 255, 255, 0.04))",
    },
    ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
      backgroundColor: "rgba(73, 143, 225, 0.45)",
    },
    "&.cm-focused": {
      outline: "none",
    },
    ".cm-cursor": {
      borderLeftColor: "var(--code-editor-caret-color, #f8f8f2)",
    },
  },
  { dark: false },
);

const syntaxTheme = HighlightStyle.define([
  { tag: tags.keyword, color: "var(--code-editor-syntax-keyword, #f92672)" },
  { tag: tags.operatorKeyword, color: "var(--code-editor-syntax-keyword, #f92672)" },
  { tag: tags.atom, color: "var(--code-editor-syntax-atom, #ae81ff)" },
  { tag: tags.bool, color: "var(--code-editor-syntax-bool, #ae81ff)" },
  { tag: tags.number, color: "var(--code-editor-syntax-number, #ae81ff)" },
  { tag: tags.string, color: "var(--code-editor-syntax-string, #e6db74)" },
  { tag: tags.special(tags.string), color: "var(--code-editor-syntax-string, #e6db74)" },
  { tag: tags.variableName, color: "var(--code-editor-syntax-variable, #f8f8f2)" },
  { tag: tags.definition(tags.variableName), color: "var(--code-editor-syntax-definition, #a6e22e)" },
  { tag: tags.propertyName, color: "var(--code-editor-syntax-property, #66d9ef)" },
  { tag: tags.function(tags.variableName), color: "var(--code-editor-syntax-function, #a6e22e)" },
  { tag: tags.className, color: "var(--code-editor-syntax-class, #a6e22e)" },
  { tag: tags.heading, color: "var(--code-editor-syntax-heading, #a6e22e)", fontWeight: "700" },
  { tag: tags.link, color: "var(--code-editor-syntax-link, #66d9ef)", textDecoration: "underline" },
  { tag: tags.emphasis, fontStyle: "italic" },
  { tag: tags.strong, fontWeight: "700" },
  { tag: tags.comment, color: "var(--code-editor-syntax-comment, #75715e)", fontStyle: "italic" },
  { tag: tags.operator, color: "var(--code-editor-syntax-operator, #f8f8f2)" },
  { tag: tags.punctuation, color: "var(--code-editor-syntax-punctuation, #f8f8f2)" },
  { tag: tags.separator, color: "var(--code-editor-syntax-separator, #f8f8f2)" },
  { tag: tags.bracket, color: "var(--code-editor-syntax-bracket, #f8f8f2)" },
  { tag: tags.brace, color: "var(--code-editor-syntax-brace, #f8f8f2)" },
]);

function createEditor(): void {
  if (!host.value) return;

  const updateListener = EditorView.updateListener.of((update: ViewUpdate) => {
    if (!update.docChanged || syncingFromParent) return;
    emit("update:modelValue", update.state.doc.toString());
  });

  view = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        lineNumbers(),
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        languageExtension.value,
        syntaxHighlighting(syntaxTheme),
        EditorState.readOnly.of(Boolean(props.readonly)),
        EditorView.editable.of(!props.readonly),
        updateListener,
        editorTheme,
      ],
    }),
  });
}

function rebuildEditor(): void {
  const parent = host.value;
  view?.destroy();
  view = null;
  if (parent) {
    createEditor();
  }
}

onMounted(createEditor);
onBeforeUnmount(() => {
  view?.destroy();
  view = null;
});

watch(
  () => props.modelValue,
  (value) => {
    if (!view || value === view.state.doc.toString()) return;
    syncingFromParent = true;
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: value },
    });
    syncingFromParent = false;
  },
);

watch([() => props.readonly, languageExtension], rebuildEditor);
</script>

<template>
  <div ref="host" class="code-editor" />
</template>
