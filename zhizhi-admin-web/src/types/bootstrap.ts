export type BootstrapState = "setup_required" | "ready" | "recovery_required";

export interface BootstrapStatus {
  state: BootstrapState;
  bootstrap_enabled: boolean;
}
