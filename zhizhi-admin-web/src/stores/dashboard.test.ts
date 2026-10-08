import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { listLLMBindingPage, listLLMEntitlements, listLLMModelPage, listScenes, listSkills } from "@/api/admin";
import { listDataSourceBindings, listDataSources } from "@/api/dataSources";
import { ApiError } from "@/api/http";
import { useDashboardStore } from "@/stores/dashboard";

vi.mock("@/api/admin", () => ({
  listLLMBindingPage: vi.fn(), listLLMEntitlements: vi.fn(), listLLMModelPage: vi.fn(),
  listScenes: vi.fn(), listSkills: vi.fn(),
}));
vi.mock("@/api/dataSources", () => ({ listDataSourceBindings: vi.fn(), listDataSources: vi.fn() }));

const access = { scenes: true, skills: true, models: true, sources: true };
const page = <T>(items: T[], total = items.length) => ({ items, pagination: { page: 1, page_size: 100, total } });

describe("tenant dashboard", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.resetAllMocks();
    vi.mocked(listScenes).mockResolvedValue([]);
    vi.mocked(listSkills).mockResolvedValue([]);
    vi.mocked(listLLMEntitlements).mockResolvedValue(page([]));
    vi.mocked(listLLMBindingPage).mockResolvedValue(page([]));
    vi.mocked(listDataSources).mockResolvedValue(page([]));
    vi.mocked(listDataSourceBindings).mockResolvedValue({ items: [] });
  });

  it("queries only the selected tenant root and uses full pagination totals", async () => {
    vi.mocked(listLLMEntitlements).mockResolvedValue(page([], 137));
    vi.mocked(listDataSources).mockResolvedValue(page([], 201));
    const store = useDashboardStore();
    await store.load("tenant-a", access);
    expect(listScenes).toHaveBeenCalledWith({ scope_type: "tenant", scope_tenant_id: "tenant-a", scope_organization_unit_id: "" });
    expect(listLLMEntitlements).toHaveBeenCalledWith("tenant-a", expect.objectContaining({ scopeType: "tenant" }));
    expect(listDataSources).toHaveBeenCalledWith(expect.objectContaining({ tenant_id: "tenant-a", organization_unit_id: "" }));
    expect(store.models.data?.count).toBe(137);
    expect(store.sources.data?.count).toBe(201);
  });

  it("keeps errors separate from empty results and other sections usable", async () => {
    vi.mocked(listScenes).mockRejectedValue(new Error("unavailable"));
    const store = useDashboardStore();
    await store.load("tenant-a", access);
    expect(store.scenes.status).toBe("error");
    expect(store.scenes.data).toBeNull();
    expect(store.skills.status).toBe("ready");
    expect(store.skills.data).toEqual([]);
  });

  it("does not call APIs without a tenant or access", async () => {
    const store = useDashboardStore();
    await store.load("", access);
    expect(listDataSources).not.toHaveBeenCalled();
    await store.load("tenant-a", { ...access, models: false });
    expect(listLLMEntitlements).not.toHaveBeenCalled();
    expect(store.models.status).toBe("forbidden");
  });

  it("shows backend access denial as forbidden, not a zero count", async () => {
    vi.mocked(listDataSources).mockRejectedValue(new ApiError(403, "denied"));
    const store = useDashboardStore();
    await store.load("tenant-a", access);
    expect(store.sources.status).toBe("forbidden");
    expect(store.sources.data).toBeNull();
  });

  it("uses the root binding's default source, even outside the resource page", async () => {
    const source = { id: "default-source", source_key: "demo", tag: "DEMO", display_name: "Demo", description: "", driver: "mysql" as const, status: "active" as const, max_rows: 500, has_credentials: true, last_test_status: "untested" };
    vi.mocked(listDataSourceBindings).mockResolvedValue({ items: [
      { tenant_id: "tenant-a", organization_unit_id: "child", source_ids: ["child-source"], default_source_id: "child-source", status: "active" },
      { tenant_id: "tenant-a", organization_unit_id: "", source_ids: [source.id], default_source_id: source.id, status: "active", sources: [source] },
    ] });
    const store = useDashboardStore();
    await store.load("tenant-a", access);
    expect(store.sources.data?.source?.tag).toBe("DEMO");
    expect(store.sources.data?.binding?.organization_unit_id).toBe("");
  });

  it("clears old tenant values immediately and ignores a late response", async () => {
    let resolveFirst!: (items: Awaited<ReturnType<typeof listScenes>>) => void;
    vi.mocked(listScenes).mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve; }));
    const store = useDashboardStore();
    const first = store.load("tenant-a", access);
    await store.load("tenant-b", access);
    resolveFirst([{ id: "stale-scene" }] as never[]);
    await first;
    expect(store.tenantId).toBe("tenant-b");
    expect(store.scenes.status).toBe("ready");
    expect(store.scenes.data).toEqual([]);
    await store.load("", access);
    expect(store.scenes.data).toBeNull();
  });

  it("resolves a default model beyond the first page instead of showing a wrong name", async () => {
    vi.mocked(listLLMBindingPage).mockResolvedValue(page([{ id: "binding", tenant_id: "tenant-a", scope_type: "tenant", organization_unit_id: "", llm_config_id: "default-model", status: "active", runtime_overrides: {} }]));
    vi.mocked(listLLMModelPage)
      .mockResolvedValueOnce(page([{ id: "other-model", display_name: "other" }] as never[], 101))
      .mockResolvedValueOnce(page([{ id: "default-model", display_name: "ds" }] as never[], 101));
    const store = useDashboardStore();
    await store.load("tenant-a", access);
    expect(store.models.data?.model?.display_name).toBe("ds");
    expect(listLLMModelPage).toHaveBeenLastCalledWith(expect.objectContaining({ tenantId: "tenant-a", page: 2 }));
  });
});
