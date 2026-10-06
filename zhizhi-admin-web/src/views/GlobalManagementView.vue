<script setup lang="ts">
import { computed, ref } from "vue";

import GitRepositoryManagementView from "@/views/GitRepositoryManagementView.vue";
import ModelManagementView from "@/views/ModelManagementView.vue";
import OrganizationView from "@/views/OrganizationView.vue";
import RolesView from "@/views/RolesView.vue";

type GlobalTab = "organization" | "roles" | "models" | "sceneGit";

const activeTab = ref<GlobalTab>("organization");
const tabs = [
  { value: "organization" as const, label: "组织管理" },
  { value: "roles" as const, label: "角色管理" },
  { value: "models" as const, label: "模型管理" },
  { value: "sceneGit" as const, label: "场景 Git" },
];
const activeTabLabel = computed(
  () => tabs.find((tab) => tab.value === activeTab.value)?.label ?? "",
);
</script>

<template>
  <div class="global-management-page">
    <header class="global-management-header">
      <div class="global-management-title">
        <h2>全局管理</h2>
        <p>维护企业组织、平台资源与权限边界</p>
      </div>
      <el-tabs
        v-model="activeTab"
        class="global-management-tabs"
        aria-label="全局管理分类"
      >
        <el-tab-pane
          v-for="item in tabs"
          :key="item.value"
          :label="item.label"
          :name="item.value"
        />
      </el-tabs>
    </header>

    <section class="global-management-body" :aria-label="activeTabLabel">
      <RolesView v-if="activeTab === 'roles'" />
      <OrganizationView v-else-if="activeTab === 'organization'" mode="global" />
      <ModelManagementView v-else-if="activeTab === 'models'" mode="global" />
      <GitRepositoryManagementView v-else mode="global" />
    </section>
  </div>
</template>

<style scoped>
.global-management-page {
  gap: 0;
  background: #fff;
}

.global-management-header {
  display: flex;
  min-height: 86px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 32px;
  border-bottom: 1px solid rgba(219, 222, 234, 0.92);
  padding: 0 34px;
  background: #fff;
}

.global-management-title {
  display: grid;
  flex: 0 0 auto;
  gap: 3px;
  padding: 0;
}

.global-management-title h2,
.global-management-title p {
  margin: 0;
}

.global-management-title h2 {
  color: var(--text-primary);
  font-size: 20px;
  font-weight: 760;
  line-height: 1.25;
}

.global-management-title p {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.global-management-tabs {
  align-self: stretch;
}

.global-management-tabs :deep(.el-tabs__header),
.global-management-tabs :deep(.el-tabs__nav-wrap),
.global-management-tabs :deep(.el-tabs__nav-scroll),
.global-management-tabs :deep(.el-tabs__nav) {
  height: 100%;
}

.global-management-tabs :deep(.el-tabs__header) {
  margin: 0;
}

.global-management-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.global-management-tabs :deep(.el-tabs__item) {
  height: 100%;
  padding: 0 22px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
}

.global-management-tabs :deep(.el-tabs__item.is-active) {
  color: var(--accent);
}

.global-management-tabs :deep(.el-tabs__active-bar) {
  height: 2px;
}

.global-management-tabs :deep(.el-tabs__content) {
  display: none;
}

@media (max-width: 1040px) {
  .global-management-header {
    min-height: auto;
    align-items: flex-start;
    flex-direction: column;
    gap: 12px;
    padding: 18px 24px 0;
  }

  .global-management-tabs {
    width: 100%;
    min-height: 42px;
  }

  .global-management-tabs :deep(.el-tabs__item) {
    padding: 0 14px;
  }
}
</style>
