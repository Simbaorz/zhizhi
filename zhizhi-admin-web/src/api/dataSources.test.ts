import { beforeEach, describe, expect, it, vi } from "vitest";
import { listDataSourceBindings, grantDataSource, saveDataSourceBinding, saveDataSource } from "@/api/dataSources";
import { fetchJson } from "@/api/http";
import type { DataSourceWrite } from "@/types/dataSources";

vi.mock("@/api/http", () => ({ fetchJson: vi.fn().mockResolvedValue({}) }));
describe("MCP data-source governance requests", () => {
  beforeEach(() => vi.clearAllMocks());
  it("keeps the current tenant and organization in authorization requests", async () => {
    const scope = { tenant_id: "tenant", organization_unit_id: "nested-leaf" };
    await grantDataSource(scope, "orders");
    expect(fetchJson).toHaveBeenCalledWith("/api/admin/data-sources/entitlements", { method: "POST", body: { ...scope, source_id: "orders" } });
    await listDataSourceBindings(scope);
    expect(fetchJson).toHaveBeenLastCalledWith("/api/admin/data-sources/bindings", { query: scope });
  });
  it("sends multiple bound sources and an explicit default without old gateway fields", async () => {
    const binding = { tenant_id: "tenant", organization_unit_id: "leaf", source_ids: ["orders", "analytics"], default_source_id: "analytics", status: "active" as const };
    await saveDataSourceBinding(binding);
    expect(fetchJson).toHaveBeenCalledWith("/api/admin/data-sources/bindings", { method: "PUT", body: binding });
  });
  it("uses the resource update route and leaves an unchanged password absent", async () => {
    const values = { source_key: "orders", tag: "OB" } as DataSourceWrite;
    await saveDataSource(values, "source/1");
    expect(fetchJson).toHaveBeenCalledWith("/api/admin/data-sources/source%2F1", { method: "PUT", body: values });
    expect(values).not.toHaveProperty("password");
  });
});
