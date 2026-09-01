<script setup lang="ts">
import { Minus, Plus } from "@element-plus/icons-vue";

import type { AdminScopeRef, ScopeTreeNode } from "@/types/admin";

defineProps<{
  node: ScopeTreeNode;
  selectedKey: string;
  expandedKeys: string[];
}>();

const emit = defineEmits<{
  toggle: [key: string];
  select: [scope: AdminScopeRef | null];
}>();

function isExpanded(key: string, expandedKeys: string[]): boolean {
  return expandedKeys.includes(key);
}
</script>

<template>
  <li>
    <div
      class="flex items-center gap-2 rounded-lg px-2 py-2 text-sm transition"
      :class="
        node.scope && node.key === selectedKey
          ? 'bg-brand/10 text-primary-text'
          : 'text-secondary-text hover:bg-muted'
      "
    >
      <el-button
        v-if="node.children.length > 0"
        class="inline-flex h-6 w-6 items-center justify-center rounded-lg text-xs text-tertiary-text hover:bg-panel"
        text
        circle
        @click="emit('toggle', node.key)"
      >
        <Minus v-if="isExpanded(node.key, expandedKeys)" aria-hidden="true" />
        <Plus v-else aria-hidden="true" />
      </el-button>
      <span v-else class="inline-block h-6 w-6"></span>
      <el-button
        class="min-w-0 flex-1 truncate text-left"
        text
        @click="node.scope ? emit('select', node.scope) : undefined"
      >
        {{ node.label }}
      </el-button>
    </div>

    <ul v-if="node.children.length > 0 && isExpanded(node.key, expandedKeys)" class="mt-1 space-y-1 pl-4">
      <ScopeTreeNode
        v-for="child in node.children"
        :key="child.key"
        :node="child"
        :selected-key="selectedKey"
        :expanded-keys="expandedKeys"
        @toggle="emit('toggle', $event)"
        @select="emit('select', $event)"
      />
    </ul>
  </li>
</template>
