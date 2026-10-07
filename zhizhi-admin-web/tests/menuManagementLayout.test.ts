import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const view = (name: string) => readFileSync(`src/views/${name}View.vue`, "utf8");

describe("menu management consistency", () => {
  it("uses centered shared forms across management menus", () => {
    for (const name of ["Organization", "Roles", "ModelManagement", "GitRepositoryManagement", "DataSources", "Skills", "Scenes", "Accounts"]) {
      const source = view(name);
      assert.match(source, /placement="modal"/, name);
      assert.doesNotMatch(source, /:placement=.*'drawer'/, name);
      assert.match(source, /admin-management-page/, name);
    }
  });

  it("keeps the tenant context in the app header and the organization tree unpaginated", () => {
    assert.doesNotMatch(view("ModelManagement"), /class="model-tenant-context"/);
    const organization = view("Organization").split('<div v-else class="organization-table-region')[1]?.split("<FormDrawer")[0] ?? "";
    assert.doesNotMatch(organization, /el-pagination|label="类型"/);
    assert.match(organization, /直属下级/);
  });

  it("presents available and running data sources as tables with explicit scope and default source", () => {
    const source = view("DataSources");
    assert.match(source, /可用数据源/);
    assert.match(source, /label="绑定数据源"/);
    assert.match(source, /label="默认数据源"/);
    assert.match(source, /label="授权范围"/);
    assert.match(source, /formScopeKey/);
    assert.match(source, /candidateLoading/);
    assert.doesNotMatch(source, /class="binding-panel"/);
  });
});
