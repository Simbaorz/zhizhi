<script setup lang="ts">
import { computed, ref } from "vue";
import {
  Coin as Database,
  Monitor as Server,
  OfficeBuilding as Building2,
  Setting as Settings2,
  Share,
  User as UsersRound,
} from "@element-plus/icons-vue";

import AppPanel from "@/components/AppPanel.vue";
import DataSourceView from "@/views/DataSourceView.vue";
import GitRepositoryManagementView from "@/views/GitRepositoryManagementView.vue";
import ModelManagementView from "@/views/ModelManagementView.vue";
import OrganizationView from "@/views/OrganizationView.vue";
import RolesView from "@/views/RolesView.vue";

type GlobalTab = "organization" | "roles" | "models" | "dataSources" | "sceneGit";

const activeTab = ref<GlobalTab>("organization");
const tabs = [
  { value: "organization" as const, label: "组织管理", icon: Building2 },
  { value: "roles" as const, label: "角色管理", icon: UsersRound },
  { value: "models" as const, label: "模型管理", icon: Server },
  { value: "dataSources" as const, label: "数据源管理", icon: Database },
  { value: "sceneGit" as const, label: "场景 Git", icon: Share },
];
const activeTabLabel = computed(
  () => tabs.find((tab) => tab.value === activeTab.value)?.label ?? "",
);
</script>

<template>
  <div class="global-management-page">
    <AppPanel class="global-management-shell">
      <header class="global-management-head">
        <el-space class="global-management-identity" alignment="center">
          <el-icon class="global-management-mark" aria-hidden="true">
            <Settings2 />
          </el-icon>
          <div class="global-management-title">
            <h2>全局管理</h2>
            <p>维护租户、组织架构、模型、数据源与平台级权限</p>
          </div>
        </el-space>
        <el-tabs
          v-model="activeTab"
          class="global-management-tabs"
          aria-label="全局管理分类"
        >
          <el-tab-pane
            v-for="item in tabs"
            :key="item.value"
            :name="item.value"
          >
            <template #label>
              <span class="global-management-tab-item">
                <el-icon aria-hidden="true">
                  <component :is="item.icon" />
                </el-icon>
                <span>{{ item.label }}</span>
              </span>
            </template>
          </el-tab-pane>
        </el-tabs>
      </header>
    </AppPanel>

    <section class="global-management-body" :aria-label="activeTabLabel">
      <RolesView v-if="activeTab === 'roles'" />
      <OrganizationView v-else-if="activeTab === 'organization'" />
      <ModelManagementView v-else-if="activeTab === 'models'" mode="global" />
      <GitRepositoryManagementView v-else-if="activeTab === 'sceneGit'" mode="global" />
      <DataSourceView v-else mode="global" />
    </section>
  </div>
</template>
