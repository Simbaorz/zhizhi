<script setup lang="ts">
import { storeToRefs } from "pinia";

import AppPanel from "@/components/AppPanel.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import StatusBanner from "@/components/StatusBanner.vue";
import { useScopeStore } from "@/stores/scope";
import { scopeKey } from "@/utils/scope";
import ScopeTreeNode from "@/features/scope-tree/ScopeTreeNode.vue";

const scopeStore = useScopeStore();
const { tree, loading, errorMessage, selectedScope, expandedKeys } = storeToRefs(scopeStore);
</script>

<template>
  <AppPanel class="flex h-full flex-col overflow-hidden">
    <header class="border-b border-border-weak px-4 py-4">
      <div class="text-sm font-semibold text-primary-text">可管理 Scope</div>
      <div class="mt-1 text-xs text-secondary-text">选择当前要操作的触点 / 省 / 市。</div>
    </header>

    <div class="app-scrollbar flex-1 overflow-y-auto px-3 py-3">
      <LoadingBlock v-if="loading" />
      <StatusBanner
        v-else-if="errorMessage"
        tone="danger"
        title="Scope 目录加载失败"
        :body="errorMessage"
      />
      <ul v-else class="space-y-1">
        <ScopeTreeNode
          v-for="node in tree"
          :key="node.key"
          :node="node"
          :selected-key="selectedScope ? scopeKey(selectedScope) : ''"
          :expanded-keys="expandedKeys"
          @toggle="scopeStore.toggleExpanded"
          @select="scopeStore.setSelectedScope"
        />
      </ul>
    </div>
  </AppPanel>
</template>
