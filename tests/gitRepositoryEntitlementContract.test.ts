import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

const apiSource = readFileSync("src/api/admin.ts", "utf-8");
const viewSource = readFileSync("src/views/GitRepositoryManagementView.vue", "utf-8");

describe("scene Git entitlement catalog", () => {
  it("loads repository and entitlement pages through the Admin API", () => {
    assert.match(apiSource, /export async function listGitRepositoryPage/);
    assert.match(
      viewSource,
      /listGitRepositoryPage\(\{[\s\S]*page:\s*repositoryPage\.value[\s\S]*pageSize:\s*GIT_PAGE_SIZE/,
    );
    assert.match(viewSource, /repositoryPagination\.value\s*=\s*result\.pagination/);
    assert.match(viewSource, /entitlementPagination\.value\s*=\s*catalog\.pagination/);
    assert.match(viewSource, /async function submitRepositorySearch[\s\S]*if \(loading\.value\) return;/);
    assert.match(viewSource, /async function submitEntitlementSearch[\s\S]*if \(loading\.value\) return;/);
    assert.doesNotMatch(viewSource, /filteredRepositories|pagedRepositories|filteredEntitlements|pagedEntitlements/);
  });

  it("uses the explicit assignable repository catalog returned by the API", () => {
    assert.match(
      apiSource,
      /assignable_repositories:\s*ManagedGitRepository\[\]/,
    );
    assert.match(
      viewSource,
      /assignableRepositories\.value\s*=\s*catalog\.assignable_repositories/,
    );
  });

  it("keeps assignment disabled when the user cannot edit or no candidate exists", () => {
    assert.doesNotMatch(
      viewSource,
      /authStore\.permissionCodes\.includes\("scene_git\.entitlements\.edit"\)/,
    );
    assert.match(
      viewSource,
      /member\.tenant_id === tenantId[\s\S]*permission\.permission_code === "scene_git\.entitlements\.edit"/,
    );
    assert.match(
      viewSource,
      /:disabled="!currentTenantId \|\| !canEditEntitlements \|\| assignableRepositories\.length === 0"/,
    );
  });
});
