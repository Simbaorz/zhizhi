export function joinRelativePath(basePath: string, name: string): string {
  const normalizedBase = basePath.trim().replace(/^\/+|\/+$/g, "");
  const normalizedName = name.trim().replace(/^\/+|\/+$/g, "");

  if (!normalizedBase) {
    return normalizedName;
  }

  if (!normalizedName) {
    return normalizedBase;
  }

  return `${normalizedBase}/${normalizedName}`;
}

export function parentRelativePath(path: string): string {
  const normalized = path.trim().replace(/^\/+|\/+$/g, "");

  if (!normalized.includes("/")) {
    return "";
  }

  return normalized.split("/").slice(0, -1).join("/");
}

export function pathSegments(path: string): string[] {
  return path
    .trim()
    .replace(/^\/+|\/+$/g, "")
    .split("/")
    .filter(Boolean);
}
