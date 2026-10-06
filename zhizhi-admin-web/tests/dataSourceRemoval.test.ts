import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const routerSource = readFileSync("src/router/index.ts", "utf-8");
const shellSource = readFileSync("src/app/AdminShell.vue", "utf-8");
const globalManagementSource = readFileSync("src/views/GlobalManagementView.vue", "utf-8");
const adminApiSource = readFileSync("src/api/admin.ts", "utf-8");
const adminTypesSource = readFileSync("src/types/admin.ts", "utf-8");

describe("data-source feature removal", () => {
  it("does not expose a management route, navigation icon, or global tab", () => {
    assert.doesNotMatch(routerSource, /DataSourceView|data-sources/);
    assert.doesNotMatch(shellSource, /data-sources/);
    assert.doesNotMatch(globalManagementSource, /DataSourceView|dataSources|数据源管理/);
  });

  it("does not retain frontend API functions or management types", () => {
    assert.doesNotMatch(adminApiSource, /DataSource|data-sources/);
    assert.doesNotMatch(adminTypesSource, /DataSource/);
  });
});
