import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getSkill } from "@/api/admin";
import { useSkillStore } from "@/stores/skill";
import type { AdminScopeRef, SkillDetail } from "@/types/admin";

vi.mock("@/api/admin", () => ({
  createSkill: vi.fn(),
  deleteSkill: vi.fn(),
  getSkill: vi.fn(),
  listSkills: vi.fn(),
  putSkill: vi.fn(),
  replaceSkillPackage: vi.fn(),
  uploadNewSkillPackage: vi.fn(),
}));

const scope: AdminScopeRef = {
  scope_type: "tenant",
  scope_tenant_id: "tenant-1",
  scope_organization_unit_id: "",
};

const skill: SkillDetail = {
  id: "skill-1",
  asset_key: "skill-1",
  name: "Skill One",
  description: "",
  status: "enabled",
  scope_type: "tenant",
  owner_user_id: null,
  path: ".skills/skill-1",
  source: "managed",
  skill_name: "skill-1",
  main_file_path: ".skills/skill-1/SKILL.md",
  content: "# Skill One",
  version: "1",
};

describe("skill store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(getSkill).mockReset();
  });

  it("keeps list loading idle while opening one skill", async () => {
    let resolveSkill: (value: SkillDetail) => void = () => undefined;
    vi.mocked(getSkill).mockReturnValue(
      new Promise((resolve) => {
        resolveSkill = resolve;
      }),
    );
    const store = useSkillStore();

    const request = store.openSkill(scope, skill.asset_key);

    expect(store.loading).toBe(false);
    expect(store.opening).toBe(true);

    resolveSkill(skill);
    await request;

    expect(store.loading).toBe(false);
    expect(store.opening).toBe(false);
    expect(store.currentSkill).toEqual(skill);
  });
});
