import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const organizationSource = readFileSync("src/views/OrganizationView.vue", "utf-8");
const globalSource = readFileSync("src/views/GlobalManagementView.vue", "utf-8");

describe("organization management layout", () => {
  it("keeps tenant lifecycle and organization hierarchy in their own modes", () => {
    assert.match(organizationSource, /租户管理/);
    assert.match(organizationSource, /组织管理/);
    assert.match(organizationSource, /class="organization-section-tabs(?:\s[^"]*)?"/);
    assert.doesNotMatch(organizationSource, /组织架构/);
    assert.match(organizationSource, /class="tenant-management-table/);
    assert.match(organizationSource, /class="organization-tree-table/);
    assert.doesNotMatch(organizationSource, /class="organization-workbench"/);
    assert.doesNotMatch(organizationSource, /class="management-card-head"/);
    assert.doesNotMatch(organizationSource, /class="tenant-context-card"/);
  });

  it("renders the hierarchy as a compact tree without duplicated row details", () => {
    assert.match(organizationSource, /row-key="id"/);
    assert.match(organizationSource, /class="organization-tree-toggle"/);
    assert.match(organizationSource, /label="外部标识"/);
    assert.match(organizationSource, /添加下级/);
    assert.doesNotMatch(organizationSource, /type="expand"/);
    assert.doesNotMatch(organizationSource, /@row-click="selectUnit"/);
    assert.doesNotMatch(organizationSource, /class="organization-inline-detail"/);
  });

  it("matches the reference density with a single toolbar directly above each table", () => {
    assert.match(organizationSource, /class="organization-primary-toolbar(?:\s[^"]*)?"/);
    assert.match(organizationSource, /class="organization-table-region(?:\s[^"]*)?"/);
    assert.match(organizationSource, /--organization-control-height: 2rem/);
    assert.match(organizationSource, /font-size: 0\.9375rem/);
    assert.doesNotMatch(organizationSource, /class="management-stack"/);
    assert.doesNotMatch(organizationSource, /class="management-kicker"/);
  });

  it("uses the shared structured drawer for tenant and organization forms", () => {
    assert.match(organizationSource, /import FormDrawer from "@\/components\/FormDrawer\.vue"/);
    assert.match(organizationSource, /<FormDrawer/);
    assert.match(organizationSource, /class="organization-drawer-form"/);
    assert.doesNotMatch(organizationSource, /<el-drawer/);
  });

  it("uses a flat global header instead of a decorated card", () => {
    assert.match(globalSource, /class="global-management-header"/);
    assert.doesNotMatch(globalSource, /<AppPanel/);
    assert.doesNotMatch(globalSource, /global-management-mark/);
    assert.doesNotMatch(globalSource, /<el-icon/);
    assert.match(organizationSource, /'is-global-mode': mode === 'global'/);
  });

  it("keeps tenant administration global while tenant routes stay scoped", () => {
    assert.match(globalSource, /<OrganizationView[^>]*mode="global"/);
    assert.match(organizationSource, /props\.mode === "global" && authStore\.isSuper/);
    assert.match(organizationSource, /scopeStore\.currentTenantId/);
  });

  it("provides first-run calls to action for tenants and organization units", () => {
    assert.match(organizationSource, /创建第一个租户/);
    assert.match(organizationSource, /创建第一个组织单元/);
  });
});
