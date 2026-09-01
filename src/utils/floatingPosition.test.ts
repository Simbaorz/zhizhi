import { describe, expect, it } from "vitest";

import { fitFloatingElementToViewport } from "@/utils/floatingPosition";

describe("fitFloatingElementToViewport", () => {
  it("moves a bottom context menu upward into the viewport", () => {
    expect(fitFloatingElementToViewport(100, 760, 180, 160, 1024, 800)).toEqual({
      x: 100,
      y: 632,
    });
  });

  it("moves a right-edge context menu left into the viewport", () => {
    expect(fitFloatingElementToViewport(980, 100, 180, 160, 1024, 800)).toEqual({
      x: 836,
      y: 100,
    });
  });

  it("keeps an oversized context menu pinned to the viewport gutter", () => {
    expect(fitFloatingElementToViewport(100, 100, 1200, 900, 1024, 800)).toEqual({
      x: 8,
      y: 8,
    });
  });
});
