import DOMPurify from "dompurify";
import type { Config } from "dompurify";

const SAFE_URI_PATTERN = /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i;
const URL_ATTRIBUTES = new Set(["href", "poster", "src", "srcset", "xlink:href"]);
const UNSAFE_URI_SCHEME = /^(?:data|javascript|vbscript):/i;

DOMPurify.addHook("uponSanitizeAttribute", (_node, attribute) => {
  if (!URL_ATTRIBUTES.has(attribute.attrName.toLowerCase())) return;
  const normalizedValue = attribute.attrValue.replace(/[\u0000-\u0020\u007f-\u009f]/g, "");
  if (UNSAFE_URI_SCHEME.test(normalizedValue)) attribute.keepAttr = false;
});

const MARKDOWN_HTML_CONFIG: Config = {
  USE_PROFILES: { html: true },
  ALLOW_UNKNOWN_PROTOCOLS: false,
  ALLOWED_URI_REGEXP: SAFE_URI_PATTERN,
  FORBID_TAGS: [
    "base",
    "button",
    "embed",
    "form",
    "iframe",
    "input",
    "link",
    "meta",
    "object",
    "script",
    "style",
    "textarea",
  ],
  FORBID_ATTR: ["form", "formaction", "srcdoc", "style"],
  RETURN_TRUSTED_TYPE: false,
};

const MERMAID_SVG_CONFIG: Config = {
  USE_PROFILES: { svg: true, svgFilters: true },
  ALLOW_UNKNOWN_PROTOCOLS: false,
  ALLOWED_URI_REGEXP: SAFE_URI_PATTERN,
  FORBID_TAGS: ["foreignObject", "iframe", "object", "script", "style"],
  FORBID_ATTR: ["form", "formaction", "srcdoc", "style"],
  RETURN_TRUSTED_TYPE: false,
};

export function sanitizeMarkdownHtml(html: string): string {
  return DOMPurify.sanitize(html, MARKDOWN_HTML_CONFIG);
}

export async function sanitizeMermaidSvg(svg: string): Promise<string> {
  return DOMPurify.sanitize(svg, MERMAID_SVG_CONFIG);
}
