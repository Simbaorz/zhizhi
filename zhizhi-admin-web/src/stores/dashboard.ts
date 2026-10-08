import { defineStore } from "pinia";
import { ref, shallowRef } from "vue";

import { listLLMBindingPage, listLLMEntitlements, listLLMModelPage, listScenes, listSkills } from "@/api/admin";
import { listDataSourceBindings, listDataSources } from "@/api/dataSources";
import { ApiError } from "@/api/http";
import type { ManagedLLMBinding, ManagedLLMConfig, WorkspaceSceneAsset, WorkspaceSkillAsset } from "@/types/admin";
import type { DataSourceBinding, DataSourceResource } from "@/types/dataSources";

export interface DashboardAccess { scenes: boolean; skills: boolean; models: boolean; sources: boolean }
export type DashboardStatus = "idle" | "loading" | "ready" | "error" | "forbidden";
export interface DashboardSection<T> { status: DashboardStatus; data: T | null }
interface ModelOverview { count: number; binding: ManagedLLMBinding | null; model: ManagedLLMConfig | null }
interface SourceOverview { count: number; binding: DataSourceBinding | null; source: DataSourceResource | null }

export const useDashboardStore = defineStore("dashboard", () => {
  const tenantId = ref("");
  const scenes = shallowRef<DashboardSection<WorkspaceSceneAsset[]>>({ status: "idle", data: null });
  const skills = shallowRef<DashboardSection<WorkspaceSkillAsset[]>>({ status: "idle", data: null });
  const models = shallowRef<DashboardSection<ModelOverview>>({ status: "idle", data: null });
  const sources = shallowRef<DashboardSection<SourceOverview>>({ status: "idle", data: null });
  let version = 0;

  async function load(id: string, access: DashboardAccess): Promise<void> {
    const requestVersion = ++version;
    tenantId.value = id;
    const scope = { scope_type: "tenant" as const, scope_tenant_id: id, scope_organization_unit_id: "" };
    async function section<T>(target: { value: DashboardSection<T> }, allowed: boolean, fetch: () => Promise<T>): Promise<void> {
      target.value = { status: !id ? "idle" : allowed ? "loading" : "forbidden", data: null };
      if (!id || !allowed) return;
      try {
        const data = await fetch();
        if (requestVersion === version) target.value = { status: "ready", data };
      } catch (error) {
        if (requestVersion === version) target.value = {
          status: error instanceof ApiError && error.status === 403 ? "forbidden" : "error", data: null,
        };
      }
    }
    await Promise.all([
      section(scenes, access.scenes, () => listScenes(scope)),
      section(skills, access.skills, () => listSkills(scope)),
      section(models, access.models, async () => {
        const [available, defaults] = await Promise.all([
          listLLMEntitlements(id, { scopeType: "tenant", pageSize: 1 }),
          listLLMBindingPage(id, { scopeType: "tenant", pageSize: 20 }),
        ]);
        const binding = defaults.items.find(item => item.tenant_id === id && item.scope_type === "tenant" && !item.organization_unit_id) ?? null;
        let model: ManagedLLMConfig | null = null;
        if (binding) {
          // The model catalog is paginated; never mistake the first page for the full catalog.
          for (let page = 1; ; page++) {
            const result = await listLLMModelPage({ tenantId: id, page, pageSize: 100 });
            model = result.items.find(item => item.id === binding.llm_config_id) ?? null;
            if (model || !result.items.length || page * 100 >= result.pagination.total || requestVersion !== version) break;
          }
        }
        return { count: available.pagination.total, binding, model };
      }),
      section(sources, access.sources, async () => {
        const sourceScope = { tenant_id: id, organization_unit_id: "" };
        const [available, defaults] = await Promise.all([
          listDataSources({ ...sourceScope, page: 1, page_size: 1, search: "" }),
          listDataSourceBindings(sourceScope),
        ]);
        const binding = defaults.items.find(item => item.tenant_id === id && !item.organization_unit_id) ?? null;
        const source = binding?.sources?.find(item => item.id === binding.default_source_id)
          ?? available.items.find(item => item.id === binding?.default_source_id) ?? null;
        return { count: available.pagination.total, binding, source };
      }),
    ]);
  }

  return { tenantId, scenes, skills, models, sources, load };
});
