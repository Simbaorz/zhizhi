import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getBootstrapStatus, initializeBootstrap } from "@/api/admin";
import { useBootstrapStore } from "@/stores/bootstrap";

vi.mock("@/api/admin", () => ({
  getBootstrapStatus: vi.fn(),
  initializeBootstrap: vi.fn(),
}));

describe("bootstrap store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("loads setup state and seals initialization after creating the root account", async () => {
    vi.mocked(getBootstrapStatus).mockResolvedValue({
      state: "setup_required",
      bootstrap_enabled: true,
    });
    vi.mocked(initializeBootstrap).mockResolvedValue({
      state: "ready",
      bootstrap_enabled: false,
    });
    const store = useBootstrapStore();

    await store.refresh();
    expect(store.state).toBe("setup_required");
    expect(store.bootstrapEnabled).toBe(true);

    const input = {
      bootstrapToken: "bootstrap-token",
      username: "admin",
      displayName: "超级管理员",
      password: "strong-password",
    };
    await store.initialize(input);

    expect(initializeBootstrap).toHaveBeenCalledWith(input);
    expect(store.state).toBe("ready");
    expect(store.bootstrapEnabled).toBe(false);
  });
});
