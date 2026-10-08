<script setup lang="ts">
import { computed, onBeforeUnmount, watch, type Component } from "vue";
import { useRouter } from "vue-router";
import { ArrowRight, Reading, Connection, Cpu, Document, Setting, Share, User, Coin } from "@element-plus/icons-vue";
import DashboardSkillIcon from "@/components/DashboardSkillIcon.vue";

import { useAuthStore } from "@/stores/auth";
import { useDashboardStore, type DashboardStatus } from "@/stores/dashboard";
import { useScopeStore } from "@/stores/scope";

const router = useRouter();
const auth = useAuthStore();
const scope = useScopeStore();
const dashboard = useDashboardStore();
const canVisit = (path: string) => auth.isSuper || auth.navigation.some(item => item.path === path);
function canReadTenantRoot(code: string): boolean {
  if (auth.isSuper) return true;
  return auth.tenantMembers.some(member => member.tenant_id === scope.currentTenantId && member.status === "active"
    && member.roles.some(role => role.role?.status !== "inactive" && role.permissions?.some(permission => permission.permission_code === code && permission.status !== "inactive"))
    && member.scopes.some(item => {
      const granted = item.scope ?? item;
      return granted.scope_type === "tenant" && granted.scope_tenant_id === scope.currentTenantId;
    }));
}
const access = computed(() => ({ scenes: canVisit("/scenes"), skills: canVisit("/skills"), models: canVisit("/models") && canReadTenantRoot("llm.view"), sources: canVisit("/data-sources") && canReadTenantRoot("data_sources.view") }));
const model = computed(() => dashboard.models.data?.model);
const modelName = computed(() => model.value?.display_name || model.value?.alias || model.value?.model_name || "模型配置不可用");
const source = computed(() => dashboard.sources.data?.source);
const sourceName = computed(() => source.value?.display_name || source.value?.source_key || "数据源配置不可用");
const modelActive = computed(() => dashboard.models.data?.binding?.status === "active" && model.value?.status === "active");
const sourceActive = computed(() => dashboard.sources.data?.binding?.status === "active" && source.value?.status === "active");
const missingWiki = computed(() => dashboard.scenes.status === "ready" && dashboard.scenes.data?.length === 0);
const unavailable = (status: DashboardStatus) => ({ idle: "请先选择租户", loading: "正在加载", error: "加载失败", forbidden: "无查看权限", ready: "" })[status];
const cards = computed<Array<{ title: string; icon: Component; count: number | null; caption: string; path: string; status: DashboardStatus; pending?: boolean }>>(() => [
  { title: "业务场景", icon: Reading, count: dashboard.scenes.data?.length ?? null, caption: missingWiki.value ? "尚未创建 Wiki" : "已登记业务场景", path: "/scenes", status: dashboard.scenes.status, pending: missingWiki.value },
  { title: "技能", icon: DashboardSkillIcon, count: dashboard.skills.data?.length ?? null, caption: dashboard.skills.data?.length ? `已登记 ${dashboard.skills.data[0]?.name || dashboard.skills.data[0]?.asset_key}${dashboard.skills.data.length > 1 ? ` 等 ${dashboard.skills.data.length} 项` : ""}` : "尚未登记技能", path: "/skills", status: dashboard.skills.status },
  { title: "可用模型", icon: Cpu, count: dashboard.models.data?.count ?? null, caption: dashboard.models.data?.binding ? `默认模型 ${modelName.value}` : "尚未设置默认模型", path: "/models", status: dashboard.models.status },
  { title: "可用数据源", icon: Coin, count: dashboard.sources.data?.count ?? null, caption: dashboard.sources.data?.binding ? "已配置默认源" : "尚未配置默认源", path: "/data-sources", status: dashboard.sources.status },
]);
const managementLinks = computed(() => [
  { title: "组织管理", icon: Connection, path: "/org" },
  { title: "账号管理", icon: User, path: "/accounts" },
  { title: "场景 Git 授权", icon: Share, path: "/scene-git" },
].filter(item => canVisit(item.path)));
function go(path: string): void { if (canVisit(path)) void router.push(path); }
function reload(): void { void dashboard.load(scope.currentTenantId, access.value); }
watch([() => scope.currentTenantId, () => scope.nodes, () => JSON.stringify(access.value)], reload, { immediate: true });
onBeforeUnmount(() => { void dashboard.load("", access.value); });
</script>

<template>
  <div class="home-workbench">
    <header class="workbench-hero">
      <div class="hero-copy">
        <span class="hero-eyebrow">工作台</span>
        <h1>让企业知识成为可执行的能力</h1>
        <p>统一管理业务知识、模型、技能与数据源。</p>
        <div class="hero-actions">
          <el-button v-if="access.scenes" type="primary" @click="go('/scenes')">配置业务场景</el-button>
          <el-button v-if="canVisit('/global')" plain @click="go('/global')">管理资源</el-button>
        </div>
      </div>
      <div class="hero-network" aria-hidden="true">
        <svg viewBox="0 0 390 180" fill="none"><path d="M78 122L205 40L332 132L78 122M205 40L205 164L332 132" stroke="currentColor" stroke-width="1"/><circle cx="137" cy="84" r="3"/><circle cx="276" cy="92" r="3"/><circle cx="206" cy="128" r="3"/><circle cx="283" cy="136" r="3"/></svg>
        <span class="network-shadow network-shadow-one"></span><span class="network-shadow network-shadow-two"></span>
        <div class="network-tile tile-knowledge"><el-icon><Document /></el-icon></div>
        <div class="network-tile tile-model"><el-icon><Cpu /></el-icon></div>
        <div class="network-tile tile-source"><el-icon><Coin /></el-icon></div>
      </div>
    </header>

    <section aria-labelledby="overview-title" class="overview-section">
      <div class="section-heading"><h2 id="overview-title">配置概览</h2><span>租户范围</span></div>
      <div class="overview-cards">
        <article v-for="card in cards" :key="card.path" class="overview-card" :aria-busy="card.status === 'loading'">
          <el-icon class="overview-icon"><component :is="card.icon" /></el-icon>
          <div class="overview-content">
            <div class="overview-label"><h3>{{ card.title }}</h3><span v-if="card.pending" class="state-badge pending">待配置</span></div>
            <strong class="overview-count">{{ card.count ?? '—' }}</strong>
            <p :class="{ 'error-text': card.status === 'error' }">{{ card.status === 'ready' ? card.caption : unavailable(card.status) }}</p>
          </div>
          <button v-if="canVisit(card.path)" class="overview-link icon-button" :aria-label="`前往${card.title}管理`" @click="go(card.path)"><el-icon><ArrowRight /></el-icon></button>
          <button v-if="card.status === 'error'" class="card-retry text-button" @click="reload">重试</button>
        </article>
      </div>
    </section>

    <div class="workbench-panels">
      <section class="workbench-panel" aria-labelledby="knowledge-title">
        <div class="panel-header"><h2 id="knowledge-title">知识与技能</h2><button v-if="access.scenes" class="text-button" @click="go('/scenes')">管理场景 <el-icon><ArrowRight /></el-icon></button></div>
        <div class="knowledge-content">
          <section class="scene-summary">
            <h3><el-icon><Document /></el-icon>业务场景 Wiki</h3>
            <div v-if="dashboard.scenes.status !== 'ready'" class="section-placeholder" role="status"><p>{{ unavailable(dashboard.scenes.status) }}</p><button v-if="dashboard.scenes.status === 'error'" class="text-button" @click="reload">重试</button></div>
            <div v-else-if="missingWiki" class="scene-empty">
              <strong>尚未创建业务场景</strong>
              <p>添加业务说明与表字典，帮助 Agent 理解查询口径和数据源标签。</p>
              <el-button plain @click="go('/scenes')">前往场景管理</el-button>
            </div>
            <div v-else class="asset-list">
              <button v-for="scene in dashboard.scenes.data?.slice(0, 3)" :key="scene.id" class="asset-row" @click="go('/scenes')"><span class="asset-icon"><el-icon><Document /></el-icon></span><span class="asset-name"><strong>{{ scene.name || scene.asset_key }}</strong><small>{{ scene.description || '业务场景 Wiki' }}</small></span><span v-if="scene.status !== 'enabled'" class="state-badge">停用</span><el-icon><ArrowRight /></el-icon></button>
              <span v-if="(dashboard.scenes.data?.length ?? 0) > 3" class="more-assets">更多场景请前往场景管理查看</span>
            </div>
          </section>
          <section class="skill-summary">
            <div class="subsection-heading"><h3><el-icon><DashboardSkillIcon /></el-icon>技能资源</h3><button v-if="access.skills" class="text-button" @click="go('/skills')">管理技能 <el-icon><ArrowRight /></el-icon></button></div>
            <div v-if="dashboard.skills.status !== 'ready'" class="section-placeholder compact" role="status"><p>{{ unavailable(dashboard.skills.status) }}</p><button v-if="dashboard.skills.status === 'error'" class="text-button" @click="reload">重试</button></div>
            <div v-else-if="!dashboard.skills.data?.length" class="section-placeholder compact"><p>尚未登记技能</p><button class="text-button" @click="go('/skills')">前往技能管理 <el-icon><ArrowRight /></el-icon></button></div>
            <div v-else class="asset-list"><button v-for="skill in dashboard.skills.data.slice(0, 3)" :key="skill.id" class="asset-row" @click="go('/skills')"><span class="asset-icon"><el-icon><Setting /></el-icon></span><span class="asset-name"><strong>{{ skill.name || skill.asset_key }}</strong><small>Skill</small></span><span v-if="skill.status !== 'enabled'" class="state-badge">停用</span><el-icon><ArrowRight /></el-icon></button><span v-if="dashboard.skills.data.length > 3" class="more-assets">更多技能请前往技能管理查看</span></div>
          </section>
        </div>
      </section>

      <section class="workbench-panel" aria-labelledby="runtime-title">
        <div class="panel-header"><h2 id="runtime-title">运行配置</h2><button v-if="access.models || access.sources" class="text-button" @click="go(access.models ? '/models' : '/data-sources')">查看配置 <el-icon><ArrowRight /></el-icon></button></div>
        <div class="runtime-content">
          <article class="runtime-card">
            <el-icon class="runtime-icon"><Cpu /></el-icon>
            <div class="runtime-detail"><h3>默认模型</h3>
              <p v-if="dashboard.models.status !== 'ready'" class="runtime-placeholder" role="status">{{ unavailable(dashboard.models.status) }}</p>
              <template v-else><div class="runtime-name"><strong>{{ dashboard.models.data?.binding ? modelName : '尚未设置默认模型' }}</strong><span v-if="dashboard.models.data?.binding" class="state-badge" :class="{ success: modelActive, pending: !model }">{{ !model ? '需检查' : modelActive ? '已设置' : '停用' }}</span></div><p class="runtime-caption">{{ dashboard.models.data?.binding ? `租户范围 · ${modelActive ? '启用' : '配置未启用'}` : '从可用模型中选择租户默认模型。' }}</p></template>
            </div><button v-if="access.models" class="text-button runtime-link" @click="go('/models')">模型管理 <el-icon><ArrowRight /></el-icon></button>
          </article>
          <article class="runtime-card">
            <el-icon class="runtime-icon"><Coin /></el-icon>
            <div class="runtime-detail"><h3>默认数据源</h3>
              <p v-if="dashboard.sources.status !== 'ready'" class="runtime-placeholder" role="status">{{ unavailable(dashboard.sources.status) }}</p>
              <template v-else><div class="runtime-name"><strong>{{ dashboard.sources.data?.binding ? sourceName : '尚未配置默认数据源' }}</strong><span v-if="dashboard.sources.data?.binding" class="state-badge" :class="{ success: sourceActive, pending: !source }">{{ !source ? '需检查' : sourceActive ? '已绑定' : '停用' }}</span><code v-if="source?.tag" class="source-tag">{{ source.tag }}</code></div><p class="runtime-caption">{{ dashboard.sources.data?.binding ? `${source?.driver === 'mysql' ? 'MySQL' : source?.driver === 'postgresql' ? 'PostgreSQL' : '数据库'} · 租户范围 · ${sourceActive ? '启用' : '配置未启用'}` : '分配可用数据源，再绑定查询源和默认源。' }}</p></template>
            </div><button v-if="access.sources" class="text-button runtime-link" @click="go('/data-sources')">数据源管理 <el-icon><ArrowRight /></el-icon></button>
          </article>
          <p class="runtime-note">Agent 按 Wiki 中的数据源标签选择查询源。</p>
        </div>
      </section>
    </div>

    <aside v-if="missingWiki" class="next-action">
      <span class="next-action-icon"><el-icon><Document /></el-icon></span>
      <div><h3>建议下一步</h3><p>补充业务场景 Wiki，让模型理解业务规则与表字典。</p></div>
      <button class="text-button" @click="go('/scenes')">去配置 <el-icon><ArrowRight /></el-icon></button>
    </aside>
    <nav v-if="managementLinks.length" class="management-shortcuts" aria-label="管理入口"><h2>管理入口</h2><button v-for="item in managementLinks" :key="item.path" @click="go(item.path)"><el-icon><component :is="item.icon" /></el-icon>{{ item.title }}<el-icon><ArrowRight /></el-icon></button></nav>
  </div>
</template>

<style scoped src="@/styles/dashboard.css"></style>
