import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { listSceneGitSyncJobs, listSkills, updateScene } from "@/api/admin";
import type { AdminScopeRef, BackgroundJob } from "@/types/admin";

describe("Admin Scene API", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { location: { origin: "https://admin.example.test" } });
    vi.stubGlobal("document", { cookie: "zhizhi_admin_csrf=csrf-token" });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("lists recent Git sync jobs for the selected Scene", async () => {
    const job = { job_id: "job-1", status: "running" } as BackgroundJob;
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ jobs: [job] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const scope: AdminScopeRef = {
      scope_type: "tenant",
      scope_tenant_id: "tenant-1",
      scope_organization_unit_id: "",
    };

    await expect(listSceneGitSyncJobs(scope, "scene/a")).resolves.toEqual([job]);

    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      "https://admin.example.test/api/admin/scenes/scene%2Fa/sync-jobs?scope_type=tenant&scope_tenant_id=tenant-1",
    );
    expect(options.method).toBe("GET");
  });

  it("normalizes shared assets to the selected tenant", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ assets: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await listSkills({
      scope_type: "organization_unit",
      scope_tenant_id: "tenant-1",
      scope_organization_unit_id: "unit-1",
    });

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      "https://admin.example.test/api/admin/skills?scope_type=tenant&scope_tenant_id=tenant-1",
    );
  });

  it("does not demote a Git Scene when updating its metadata", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          asset_key: "scene-git",
          source: "git",
          required_skill_asset_key: "skill-wiki",
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await updateScene(
      {
        scope_type: "tenant",
        scope_tenant_id: "tenant-1",
        scope_organization_unit_id: "",
      },
      "scene-git",
      { requiredSkillAssetKey: "skill-wiki" },
    );

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(options.body)) as Record<string, unknown>;
    expect(body).not.toHaveProperty("source");
    expect(body.required_skill_asset_key).toBe("skill-wiki");
  });
});
