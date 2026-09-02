import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getScopeCatalog } from "@/api/admin";
import { useScopeStore } from "@/stores/scope";

vi.mock("@/api/admin", () => ({
  getScopeCatalog: vi.fn(),
}));

describe("scope store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(getScopeCatalog).mockReset();
  });

  it("clears a stale selected scope when the catalog has no tenants", async () => {
    vi.mocked(getScopeCatalog).mockResolvedValue([]);
    const store = useScopeStore();
    store.setSelectedScope({
      scope_type: "tenant",
      scope_tenant_id: "stale-tenant-id",
      scope_organization_unit_id: "",
    });

    await store.fetchCatalog();

    expect(store.currentTenantScope).toBeNull();
    expect(store.selectedScope).toBeNull();
    expect(store.selectedAssetTenantScope).toBeNull();
  });
});
