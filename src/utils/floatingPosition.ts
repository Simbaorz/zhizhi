export interface FloatingPosition {
  x: number;
  y: number;
}

export function fitFloatingElementToViewport(
  anchorX: number,
  anchorY: number,
  elementWidth: number,
  elementHeight: number,
  viewportWidth: number,
  viewportHeight: number,
  gutter = 8,
): FloatingPosition {
  const maxX = Math.max(gutter, viewportWidth - elementWidth - gutter);
  const maxY = Math.max(gutter, viewportHeight - elementHeight - gutter);
  return {
    x: Math.min(Math.max(anchorX, gutter), maxX),
    y: Math.min(Math.max(anchorY, gutter), maxY),
  };
}
