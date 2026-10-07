import { fetchJson } from "@/api/http";
import type { DataSourceBinding, DataSourcePage, DataSourceResource, DataSourceScope, DataSourceWrite } from "@/types/dataSources";

const BASE = "/api/admin/data-sources";
export function listDataSources(query: { page: number; page_size: number; search: string; tenant_id?: string; organization_unit_id?: string }): Promise<DataSourcePage> {
  return fetchJson(BASE, { query });
}
export function saveDataSource(values: DataSourceWrite, id?: string): Promise<DataSourceResource> {
  return fetchJson(id ? `${BASE}/${encodeURIComponent(id)}` : BASE, { method: id ? "PUT" : "POST", body: values });
}
export function deleteDataSource(id: string): Promise<{ deleted: boolean }> {
  return fetchJson(`${BASE}/${encodeURIComponent(id)}`, { method: "DELETE" });
}
export function testDataSource(id: string): Promise<{ success: boolean; message: string }> {
  return fetchJson(`${BASE}/${encodeURIComponent(id)}/test`, { method: "POST" });
}
export function listAssignableDataSources(scope: DataSourceScope, page: number, search: string): Promise<DataSourcePage> {
  return fetchJson(`${BASE}/assignable`, { query: { ...scope, page, page_size: 50, search } });
}
export function grantDataSource(scope: DataSourceScope, sourceId: string): Promise<unknown> {
  return fetchJson(`${BASE}/entitlements`, { method: "POST", body: { ...scope, source_id: sourceId } });
}
export function revokeDataSource(scope: DataSourceScope, sourceId: string): Promise<unknown> {
  return fetchJson(`${BASE}/entitlements`, { method: "DELETE", query: { ...scope, source_id: sourceId } });
}
export function listDataSourceBindings(scope: DataSourceScope): Promise<{ items: DataSourceBinding[] }> {
  return fetchJson(`${BASE}/bindings`, { query: { ...scope } });
}
export function saveDataSourceBinding(binding: DataSourceBinding): Promise<DataSourceBinding> {
  return fetchJson(`${BASE}/bindings`, { method: "PUT", body: binding });
}
export function deleteDataSourceBinding(scope: DataSourceScope): Promise<unknown> {
  return fetchJson(`${BASE}/bindings`, { method: "DELETE", query: { ...scope } });
}
