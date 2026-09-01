<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import {
  Delete as Trash2,
  Edit as Pencil,
  Key as KeyRound,
  Plus,
  Refresh as RotateCcw,
  Search,
  Share,
  SwitchButton,
} from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";
import { storeToRefs } from "pinia";

import {
  createGitEntitlements,
  createGitRepository,
  deleteGitEntitlement,
  deleteGitRepository,
  listGitEntitlements,
  listGitRepositoryPage,
  testGitRepository,
  updateGitEntitlement,
  updateGitRepository,
  updateGitRepositoryCredentials,
} from "@/api/admin";
import { ApiError } from "@/api/http";
import AppPanel from "@/components/AppPanel.vue";
import FormDrawer from "@/components/FormDrawer.vue";
import LoadingBlock from "@/components/LoadingBlock.vue";
import StatusBanner from "@/components/StatusBanner.vue";
import { useAuthStore } from "@/stores/auth";
import { useScopeStore } from "@/stores/scope";
import { useUiStore } from "@/stores/ui";
import type { ManagedGitEntitlement, ManagedGitRepository, PaginationInfo } from "@/types/admin";
import { formatDate } from "@/utils/format";
import { tenantScopeDisplayLabel } from "@/utils/scope";

type DrawerMode = "create" | "edit" | "credentials" | "entitlement-create";

const GIT_PAGE_SIZE = 10;

const statusFilterOptions = [
  { label: "全部", value: "all" },
  { label: "启用", value: "active" },
  { label: "停用", value: "inactive" },
] as const;

const props = withDefaults(defineProps<{ mode?: "domain" | "global" }>(), {
  mode: "domain",
});

const authStore = useAuthStore();
const scopeStore = useScopeStore();
const uiStore = useUiStore();
const scopeRefs = storeToRefs(scopeStore);

const isGlobalMode = computed(() => props.mode === "global");
const currentTenantId = computed(() => scopeRefs.currentTenantId.value);
const currentTenantLabel = computed(() => {
  const scope = scopeRefs.currentTenantScope.value;
  return scope ? tenantScopeDisplayLabel(scope, scopeRefs.nodes.value) : "未选择租户";
});
const canEditEntitlements = computed(() => {
  if (authStore.isSuper) return true;
  const tenantId = currentTenantId.value;
  return authStore.tenantMembers.some(
    (member) =>
      member.status === "active"
      && member.tenant_id === tenantId
      && member.scopes.some(
        (binding) =>
          binding.scope?.scope_type === "tenant"
          && binding.scope.scope_tenant_id === tenantId,
      )
      && member.roles.some(
        (role) =>
          (!role.role || role.role.status === "active")
          && (role.permissions ?? []).some(
            (permission) => permission.permission_code === "scene_git.entitlements.edit",
          ),
      ),
  );
});

const loading = ref(false);
const saving = ref(false);
const testingId = ref("");
const errorMessage = ref("");
const repositories = ref<ManagedGitRepository[]>([]);
const entitlements = ref<ManagedGitEntitlement[]>([]);
const assignableRepositories = ref<ManagedGitRepository[]>([]);
const repositorySearchInput = ref("");
const repositorySearch = ref("");
const repositoryStatusInput = ref<"all" | "active" | "inactive">("all");
const repositoryStatus = ref<"all" | "active" | "inactive">("all");
const entitlementSearchInput = ref("");
const entitlementSearch = ref("");
const entitlementStatusInput = ref<"all" | "active" | "inactive">("all");
const entitlementStatus = ref<"all" | "active" | "inactive">("all");
const repositoryPage = ref(1);
const entitlementPage = ref(1);
const repositoryPagination = ref<PaginationInfo>({ page: 1, page_size: GIT_PAGE_SIZE, total: 0 });
const entitlementPagination = ref<PaginationInfo>({ page: 1, page_size: GIT_PAGE_SIZE, total: 0 });
const drawerOpen = ref(false);
const drawerMode = ref<DrawerMode | null>(null);
const selectedRepository = ref<ManagedGitRepository | null>(null);

const repositoryForm = reactive({
  alias: "",
  displayName: "",
  repoUrl: "",
  defaultBranch: "",
  username: "",
  password: "",
  status: "active" as "active" | "inactive",
});
const credentialForm = reactive({ username: "", password: "" });
const entitlementForm = reactive({
  repositoryIds: [] as string[],
  status: "active" as "active" | "inactive",
});

const repositoryPageCount = computed(() => Math.max(1, Math.ceil(repositoryPagination.value.total / GIT_PAGE_SIZE)));
const entitlementPageCount = computed(() => Math.max(1, Math.ceil(entitlementPagination.value.total / GIT_PAGE_SIZE)));
const drawerTitle = computed(() => {
  if (drawerMode.value === "create") return "新增场景 Git 仓库";
  if (drawerMode.value === "edit") return "编辑场景 Git 仓库";
  if (drawerMode.value === "credentials") return "更新仓库凭据";
  if (drawerMode.value === "entitlement-create") return "分配场景 Git 仓库";
  return "";
});
const drawerSubtitle = computed(() =>
  drawerMode.value === "entitlement-create"
    ? `分配到当前租户：${currentTenantLabel.value}`
    : selectedRepository.value?.display_name || selectedRepository.value?.alias || "",
);

function repositoryName(repositoryId: string): string {
  const repository = repositories.value.find((item) => item.id === repositoryId);
  return repository?.display_name || repository?.alias || repositoryId;
}

function repositoryUrl(repositoryId: string): string {
  return repositories.value.find((item) => item.id === repositoryId)?.repo_url || "-";
}

async function refresh(): Promise<void> {
  loading.value = true;
  errorMessage.value = "";
  try {
    if (isGlobalMode.value) {
      let result = await listGitRepositoryPage({
        search: repositorySearch.value,
        status: repositoryStatus.value,
        page: repositoryPage.value,
        pageSize: GIT_PAGE_SIZE,
      });
      repositories.value = result.items;
      repositoryPagination.value = result.pagination;
      if (repositoryPage.value > repositoryPageCount.value && result.pagination.total > 0) {
        repositoryPage.value = repositoryPageCount.value;
        result = await listGitRepositoryPage({
          search: repositorySearch.value,
          status: repositoryStatus.value,
          page: repositoryPage.value,
          pageSize: GIT_PAGE_SIZE,
        });
        repositories.value = result.items;
        repositoryPagination.value = result.pagination;
      }
      entitlements.value = [];
      assignableRepositories.value = [];
    } else if (currentTenantId.value) {
      let catalog = await listGitEntitlements(currentTenantId.value, {
        search: entitlementSearch.value,
        status: entitlementStatus.value,
        page: entitlementPage.value,
        pageSize: GIT_PAGE_SIZE,
      });
      repositories.value = catalog.repositories;
      entitlements.value = catalog.entitlements;
      assignableRepositories.value = catalog.assignable_repositories;
      entitlementPagination.value = catalog.pagination;
      if (entitlementPage.value > entitlementPageCount.value && catalog.pagination.total > 0) {
        entitlementPage.value = entitlementPageCount.value;
        catalog = await listGitEntitlements(currentTenantId.value, {
          search: entitlementSearch.value,
          status: entitlementStatus.value,
          page: entitlementPage.value,
          pageSize: GIT_PAGE_SIZE,
        });
        repositories.value = catalog.repositories;
        entitlements.value = catalog.entitlements;
        assignableRepositories.value = catalog.assignable_repositories;
        entitlementPagination.value = catalog.pagination;
      }
    } else {
      repositories.value = [];
      entitlements.value = [];
      assignableRepositories.value = [];
      entitlementPagination.value = { page: 1, page_size: GIT_PAGE_SIZE, total: 0 };
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "场景 Git 数据加载失败。";
  } finally {
    loading.value = false;
  }
}

async function submitRepositorySearch(): Promise<void> {
  if (loading.value) return;
  repositorySearch.value = repositorySearchInput.value.trim();
  repositoryStatus.value = repositoryStatusInput.value;
  repositoryPage.value = 1;
  await refresh();
}

async function resetRepositorySearch(): Promise<void> {
  if (loading.value) return;
  repositorySearchInput.value = "";
  repositoryStatusInput.value = "all";
  repositorySearch.value = "";
  repositoryStatus.value = "all";
  repositoryPage.value = 1;
  await refresh();
}

async function submitEntitlementSearch(): Promise<void> {
  if (loading.value) return;
  entitlementSearch.value = entitlementSearchInput.value.trim();
  entitlementStatus.value = entitlementStatusInput.value;
  entitlementPage.value = 1;
  await refresh();
}

async function resetEntitlementSearch(): Promise<void> {
  if (loading.value) return;
  entitlementSearchInput.value = "";
  entitlementStatusInput.value = "all";
  entitlementSearch.value = "";
  entitlementStatus.value = "all";
  entitlementPage.value = 1;
  await refresh();
}

async function setRepositoryPage(page: number): Promise<void> {
  if (loading.value) return;
  repositoryPage.value = Math.min(Math.max(page, 1), repositoryPageCount.value);
  await refresh();
}

async function setEntitlementPage(page: number): Promise<void> {
  if (loading.value) return;
  entitlementPage.value = Math.min(Math.max(page, 1), entitlementPageCount.value);
  await refresh();
}

function openCreate(): void {
  selectedRepository.value = null;
  Object.assign(repositoryForm, {
    alias: "",
    displayName: "",
    repoUrl: "",
    defaultBranch: "",
    username: "",
    password: "",
    status: "active",
  });
  drawerMode.value = "create";
  drawerOpen.value = true;
}

function openEdit(repository: ManagedGitRepository): void {
  selectedRepository.value = repository;
  Object.assign(repositoryForm, {
    alias: repository.alias,
    displayName: repository.display_name,
    repoUrl: repository.repo_url,
    defaultBranch: repository.default_branch,
    username: "",
    password: "",
    status: repository.status === "inactive" ? "inactive" : "active",
  });
  drawerMode.value = "edit";
  drawerOpen.value = true;
}

function openCredentials(repository: ManagedGitRepository): void {
  selectedRepository.value = repository;
  credentialForm.username = repository.username;
  credentialForm.password = "";
  drawerMode.value = "credentials";
  drawerOpen.value = true;
}

function openEntitlementCreate(): void {
  entitlementForm.repositoryIds = [];
  entitlementForm.status = "active";
  drawerMode.value = "entitlement-create";
  drawerOpen.value = true;
}

function closeDrawer(): void {
  drawerOpen.value = false;
}

async function submitDrawer(): Promise<void> {
  saving.value = true;
  errorMessage.value = "";
  try {
    if (drawerMode.value === "create") {
      await createGitRepository(repositoryForm);
      uiStore.pushNotice({ tone: "success", title: "场景 Git 仓库已创建" });
    } else if (drawerMode.value === "edit" && selectedRepository.value) {
      await updateGitRepository(selectedRepository.value.id, repositoryForm);
      uiStore.pushNotice({ tone: "success", title: "场景 Git 仓库已更新" });
    } else if (drawerMode.value === "credentials" && selectedRepository.value) {
      await updateGitRepositoryCredentials(selectedRepository.value.id, credentialForm);
      uiStore.pushNotice({ tone: "success", title: "仓库凭据已更新" });
    } else if (drawerMode.value === "entitlement-create" && currentTenantId.value) {
      await createGitEntitlements({
        tenantId: currentTenantId.value,
        gitRepositoryIds: entitlementForm.repositoryIds,
        status: entitlementForm.status,
      });
      uiStore.pushNotice({ tone: "success", title: "场景 Git 仓库已分配" });
    }
    closeDrawer();
    await refresh();
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "场景 Git 操作失败。";
  } finally {
    saving.value = false;
  }
}

async function runTest(repository: ManagedGitRepository): Promise<void> {
  testingId.value = repository.id;
  try {
    const result = await testGitRepository(repository.id);
    uiStore.pushNotice({
      tone: result.ok ? "success" : "danger",
      title: result.ok ? "仓库连接成功" : "仓库连接失败",
      body: result.message,
    });
    await refresh();
  } catch (error) {
    uiStore.pushNotice({
      tone: "danger",
      title: "仓库测试失败",
      body: error instanceof Error ? error.message : "",
    });
  } finally {
    testingId.value = "";
  }
}

async function removeRepository(repository: ManagedGitRepository): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除场景 Git 仓库“${repository.display_name || repository.alias}”？`,
      "确认操作",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  try {
    await deleteGitRepository(repository.id);
    uiStore.pushNotice({ tone: "success", title: "场景 Git 仓库已删除" });
    await refresh();
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "删除场景 Git 仓库失败。";
  }
}

async function toggleEntitlement(entitlement: ManagedGitEntitlement): Promise<void> {
  const status = entitlement.status === "active" ? "inactive" : "active";
  try {
    await updateGitEntitlement(entitlement.id, status);
    await refresh();
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "更新场景 Git 授权失败。";
  }
}

async function removeEntitlement(entitlement: ManagedGitEntitlement): Promise<void> {
  try {
    await ElMessageBox.confirm("确认取消当前租户的场景 Git 仓库授权？", "确认操作", {
      type: "warning",
      confirmButtonText: "确认",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  try {
    await deleteGitEntitlement(entitlement.id);
    await refresh();
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "取消场景 Git 授权失败。";
  }
}

watch(currentTenantId, async () => {
  if (!isGlobalMode.value) {
    entitlementPage.value = 1;
    await refresh();
  }
});

onMounted(refresh);
</script>

<template>
  <div class="model-page scene-git-page">
    <StatusBanner
      v-if="errorMessage"
      tone="danger"
      title="场景 Git 管理异常"
      :body="errorMessage"
    />

    <AppPanel v-if="!isGlobalMode" class="global-management-shell model-management-shell">
      <header class="global-management-head model-management-head">
        <el-space class="global-management-identity" alignment="center">
          <el-icon class="global-management-mark" aria-hidden="true"><Share /></el-icon>
          <div class="global-management-title">
            <h2>场景 Git 授权</h2>
            <p>维护当前租户可用于业务场景的 Git 仓库</p>
          </div>
        </el-space>
      </header>
    </AppPanel>

    <AppPanel class="model-list-panel">
      <header class="model-toolbar">
        <div class="model-toolbar-title">
          <h2>{{ isGlobalMode ? "场景 Git 仓库" : "可用场景 Git" }}</h2>
        </div>
        <div class="model-toolbar-actions admin-toolbar-layout">
          <div v-if="isGlobalMode" class="admin-filter-group">
            <el-input
              v-model="repositorySearchInput"
              class="admin-toolbar-search"
              type="search"
              clearable
              placeholder="搜索名称 / 别名 / 地址"
              @keydown.enter.prevent="submitRepositorySearch"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-segmented v-model="repositoryStatusInput" :options="statusFilterOptions" aria-label="状态筛选" />
            <el-button :icon="RotateCcw" :disabled="loading" @click="resetRepositorySearch">重置</el-button>
            <el-button type="primary" :icon="Search" :disabled="loading" @click="submitRepositorySearch">搜索</el-button>
          </div>
          <div v-else class="admin-filter-group">
            <el-input
              v-model="entitlementSearchInput"
              class="admin-toolbar-search"
              type="search"
              clearable
              placeholder="搜索仓库名称 / 别名 / 地址"
              @keydown.enter.prevent="submitEntitlementSearch"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-segmented v-model="entitlementStatusInput" :options="statusFilterOptions" aria-label="状态筛选" />
            <el-button :icon="RotateCcw" :disabled="loading" @click="resetEntitlementSearch">重置</el-button>
            <el-button type="primary" :icon="Search" :disabled="loading" @click="submitEntitlementSearch">搜索</el-button>
          </div>
          <div class="admin-action-group">
            <el-button v-if="isGlobalMode" type="primary" :icon="Plus" @click="openCreate">新增仓库</el-button>
            <el-button
              v-else
              type="primary"
              :icon="Plus"
              :disabled="!currentTenantId || !canEditEntitlements || assignableRepositories.length === 0"
              @click="openEntitlementCreate"
            >
              分配仓库
            </el-button>
          </div>
        </div>
      </header>

      <LoadingBlock v-if="loading" />

      <template v-else-if="isGlobalMode">
        <div class="admin-table-region">
          <el-table class="admin-data-table" :data="repositories" height="100%" stripe row-key="id">
            <el-table-column label="仓库" min-width="230">
              <template #default="{ row }">
                <el-space direction="vertical" alignment="start" :size="2">
                  <strong>{{ row.display_name || row.alias }}</strong>
                  <el-text type="info" size="small">别名 {{ row.alias }}</el-text>
                </el-space>
              </template>
            </el-table-column>
            <el-table-column prop="repo_url" label="仓库地址" min-width="300" show-overflow-tooltip />
            <el-table-column label="凭据" min-width="110">
              <template #default="{ row }">
                <el-tag :type="row.has_credential ? 'success' : 'info'" effect="light">
                  {{ row.has_credential ? "已配置" : "无需凭据" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" min-width="90">
              <template #default="{ row }">
                <el-tag :type="row.status === 'active' ? 'success' : 'info'" effect="light">
                  {{ row.status === "active" ? "启用" : "停用" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="测试" min-width="190" show-overflow-tooltip>
              <template #default="{ row }">
                <el-space direction="vertical" alignment="start" :size="2">
                  <el-tag :type="row.last_test_status === 'succeeded' ? 'success' : row.last_test_status === 'failed' ? 'danger' : 'info'" effect="light">
                    {{ row.last_test_status === "succeeded" ? "成功" : row.last_test_status === "failed" ? "失败" : "未测试" }}
                  </el-tag>
                  <el-text type="info" size="small">{{ row.last_test_message || "尚未执行测试" }}</el-text>
                </el-space>
              </template>
            </el-table-column>
            <el-table-column label="更新时间" min-width="160">
              <template #default="{ row }">{{ formatDate(row.updated_at ?? undefined) }}</template>
            </el-table-column>
            <el-table-column label="操作" align="right" min-width="270">
              <template #default="{ row }">
                <el-space :size="8" wrap>
                  <el-button link type="primary" :loading="testingId === row.id" @click="runTest(row)">测试</el-button>
                  <el-button link type="primary" :icon="KeyRound" @click="openCredentials(row)">凭据</el-button>
                  <el-button link type="primary" :icon="Pencil" @click="openEdit(row)">编辑</el-button>
                  <el-button link type="danger" :icon="Trash2" @click="removeRepository(row)">删除</el-button>
                </el-space>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="暂无场景 Git 仓库">
                <span class="admin-empty-description">新增仓库后，可在租户范围内分配给业务场景使用。</span>
              </el-empty>
            </template>
          </el-table>
        </div>
        <el-pagination
          v-if="repositoryPagination.total > 0"
          class="admin-pagination"
          :current-page="repositoryPage"
          :page-size="GIT_PAGE_SIZE"
          :total="repositoryPagination.total"
          layout="total, prev, pager, next"
          @current-change="setRepositoryPage"
        />
      </template>

      <template v-else>
        <el-empty v-if="!currentTenantId" description="请先在顶部选择当前租户。" />
        <div v-else class="admin-table-region">
          <el-table class="admin-data-table" :data="entitlements" height="100%" stripe row-key="id">
            <el-table-column label="场景 Git 仓库" min-width="260">
              <template #default="{ row }">
                <el-space direction="vertical" alignment="start" :size="2">
                  <strong>{{ repositoryName(row.git_repository_id) }}</strong>
                  <el-text type="info" size="small">{{ repositoryUrl(row.git_repository_id) }}</el-text>
                </el-space>
              </template>
            </el-table-column>
            <el-table-column label="授权级别" min-width="120"><template #default><el-tag effect="plain">租户级</el-tag></template></el-table-column>
            <el-table-column label="状态" min-width="110">
              <template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'" effect="light">{{ row.status === "active" ? "启用" : "停用" }}</el-tag></template>
            </el-table-column>
            <el-table-column label="更新时间" min-width="170"><template #default="{ row }">{{ formatDate(row.updated_at ?? undefined) }}</template></el-table-column>
            <el-table-column v-if="canEditEntitlements" label="操作" align="right" min-width="210">
              <template #default="{ row }">
                <el-space :size="8">
                  <el-button link type="primary" :icon="SwitchButton" @click="toggleEntitlement(row)">{{ row.status === "active" ? "停用" : "启用" }}</el-button>
                  <el-button link type="danger" :icon="Trash2" @click="removeEntitlement(row)">取消分配</el-button>
                </el-space>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="当前租户暂无可用场景 Git">
                <span class="admin-empty-description">从全局场景 Git 仓库中分配后，业务场景即可选择使用。</span>
              </el-empty>
            </template>
          </el-table>
        </div>
        <el-pagination
          v-if="currentTenantId && entitlementPagination.total > 0"
          class="admin-pagination"
          :current-page="entitlementPage"
          :page-size="GIT_PAGE_SIZE"
          :total="entitlementPagination.total"
          layout="total, prev, pager, next"
          @current-change="setEntitlementPage"
        />
      </template>
    </AppPanel>

    <FormDrawer
      :open="drawerOpen"
      :title="drawerTitle"
      :subtitle="drawerSubtitle"
      :saving="saving"
      :submit-disabled="drawerMode === 'entitlement-create' && entitlementForm.repositoryIds.length === 0"
      :submit-text="drawerMode === 'entitlement-create' ? '保存分配' : '保存'"
      @close="closeDrawer"
      @submit="submitDrawer"
    >
      <el-form v-if="drawerMode === 'create' || drawerMode === 'edit'" label-position="top">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12"><el-form-item label="仓库别名" required><el-input v-model="repositoryForm.alias" :disabled="drawerMode === 'edit'" placeholder="main-scenes" /></el-form-item></el-col>
          <el-col :xs="24" :sm="12"><el-form-item label="显示名称" required><el-input v-model="repositoryForm.displayName" placeholder="主场景仓库" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="仓库地址" required><el-input v-model="repositoryForm.repoUrl" placeholder="http://git.internal/group/repo.git" /></el-form-item></el-col>
          <el-col :xs="24" :sm="12"><el-form-item label="默认分支"><el-input v-model="repositoryForm.defaultBranch" placeholder="main" /></el-form-item></el-col>
          <el-col :xs="24" :sm="12"><el-form-item label="状态"><el-select v-model="repositoryForm.status" style="width: 100%"><el-option value="active" label="启用" /><el-option value="inactive" label="停用" /></el-select></el-form-item></el-col>
          <template v-if="drawerMode === 'create'">
            <el-col :xs="24" :sm="12"><el-form-item label="用户名"><el-input v-model="repositoryForm.username" autocomplete="off" /></el-form-item></el-col>
            <el-col :xs="24" :sm="12"><el-form-item label="密码 / Token"><el-input v-model="repositoryForm.password" type="password" show-password autocomplete="new-password" /></el-form-item></el-col>
          </template>
        </el-row>
      </el-form>

      <el-form v-else-if="drawerMode === 'credentials'" label-position="top">
        <el-alert title="密码留空则保留原 Token；用户名和密码都清空将清除凭据" type="info" :closable="false" show-icon />
        <el-form-item label="用户名"><el-input v-model="credentialForm.username" autocomplete="off" /></el-form-item>
        <el-form-item label="密码 / Token"><el-input v-model="credentialForm.password" type="password" show-password autocomplete="new-password" /></el-form-item>
      </el-form>

      <el-form v-else label-position="top">
        <el-alert :title="`当前租户：${currentTenantLabel}`" type="info" :closable="false" show-icon />
        <el-form-item label="可用场景 Git 仓库" required>
          <el-select v-model="entitlementForm.repositoryIds" multiple filterable collapse-tags collapse-tags-tooltip style="width: 100%">
            <el-option v-for="item in assignableRepositories" :key="item.id" :value="item.id" :label="item.display_name || item.alias" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态"><el-select v-model="entitlementForm.status" style="width: 100%"><el-option value="active" label="启用" /><el-option value="inactive" label="停用" /></el-select></el-form-item>
      </el-form>
    </FormDrawer>
  </div>
</template>

<style scoped>
.model-page {
  --admin-toolbar-control-height: 2rem;
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  gap: 10px;
  overflow: hidden;
}

:global(.global-management-body) .model-page {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.model-management-shell {
  flex: 0 0 auto;
}

.model-list-panel {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
  border-radius: 10px;
  box-shadow: none;
}

.model-list-panel :deep(.el-card__body) {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
}

.model-toolbar {
  display: grid;
  min-height: 3.375rem;
  grid-template-columns: minmax(8rem, 1fr) minmax(0, max-content) minmax(8rem, 1fr);
  align-items: center;
  gap: 0.75rem;
  border-bottom: 1px solid rgba(215, 222, 226, 0.92);
  background: #ffffff;
  padding: 0.75rem 0.875rem;
}

.model-toolbar-title {
  min-width: 7rem;
  grid-column: 1;
}

.model-toolbar-title h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 780;
  line-height: 1.2;
}

.model-toolbar-actions.admin-toolbar-layout {
  display: contents !important;
}

.model-page .admin-filter-group {
  grid-column: 2;
  flex-wrap: nowrap;
  justify-self: center;
}

.model-page .admin-action-group {
  grid-column: 3;
  flex-wrap: nowrap;
  justify-self: end;
}

.model-page .admin-toolbar-search.el-input {
  width: clamp(14rem, 22vw, 22rem);
}

.model-toolbar :deep(.el-segmented),
.model-toolbar :deep(.el-segmented__item),
.model-page .admin-filter-group > .el-button,
.model-page .admin-action-group > .el-button {
  min-height: var(--admin-toolbar-control-height);
}

.model-page .admin-table-region {
  height: 0;
  min-height: 0;
  flex: 1 1 0;
  overflow: hidden;
}

.model-page .admin-data-table.el-table {
  width: 100%;
  min-height: 0;
  --el-table-header-bg-color: #f4f8f8;
  --el-table-header-text-color: var(--text-secondary);
  --el-table-row-hover-bg-color: rgba(91, 91, 214, 0.05);
  --el-table-border-color: rgba(220, 229, 232, 0.9);
}

.model-page .admin-data-table :deep(.el-table__header-wrapper th.el-table__cell) {
  background: var(--el-table-header-bg-color);
  font-size: 0.8125rem;
  font-weight: 760;
}

.model-page .admin-data-table :deep(.el-table__cell) {
  padding-block: 0.625rem;
}

.model-page .admin-data-table :deep(.el-button.is-link) {
  min-height: auto;
  padding: 0;
  font-weight: 650;
}

.model-page .admin-pagination {
  display: flex;
  flex: 0 0 auto;
  justify-content: flex-end;
  padding: 0.75rem 1rem;
  border-top: 1px solid rgba(220, 229, 232, 0.9);
}

.model-page .admin-table-region + .admin-pagination {
  border-top: 0;
}

@media (max-width: 1380px) {
  .model-page .admin-toolbar-layout {
    display: flex !important;
    flex-wrap: wrap;
    justify-content: flex-end !important;
  }

  .model-page .admin-filter-group {
    flex: 1 1 auto;
    flex-wrap: wrap;
    justify-content: center;
  }
}

@media (max-width: 720px) {
  .model-toolbar {
    display: flex;
    align-items: stretch;
    flex-direction: column;
  }

  .model-page .admin-filter-group,
  .model-page .admin-action-group,
  .model-page .admin-toolbar-search.el-input {
    width: 100%;
  }

  .model-page .admin-filter-group > .el-button,
  .model-page .admin-action-group > .el-button {
    flex: 1 1 auto;
  }
}
</style>
