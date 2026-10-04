// Content-Security-Policy for a ui:// view, built from its `_meta.ui.csp`
// (MCP Apps 2026-01-26, "Content Security Policy"). Hosts must not loosen it.

export interface ResourceCsp {
  connectDomains?: string[];
  resourceDomains?: string[];
  frameDomains?: string[];
  baseUriDomains?: string[];
}

// Origins only (scheme + host + optional port, wildcard subdomain allowed):
// anything else could inject directives into the header.
const ORIGIN = /^https?:\/\/(\*\.)?[a-z0-9.-]+(:\d+)?$/i;

const clean = (domains: unknown): string[] =>
  Array.isArray(domains) ? domains.filter((d): d is string => typeof d === "string" && ORIGIN.test(d)) : [];

export function parseCsp(raw: string | null): ResourceCsp {
  if (!raw) return {};
  try {
    const value = JSON.parse(raw) as Record<string, unknown>;
    return {
      connectDomains: clean(value.connectDomains),
      resourceDomains: clean(value.resourceDomains),
      frameDomains: clean(value.frameDomains),
      baseUriDomains: clean(value.baseUriDomains),
    };
  } catch {
    return {};
  }
}

export function buildCsp(csp: ResourceCsp): string {
  const res = (csp.resourceDomains ?? []).join(" ");
  const join = (...parts: string[]) => parts.filter(Boolean).join(" ");
  return [
    "default-src 'none'",
    `script-src ${join("'self'", "'unsafe-inline'", res)}`,
    `style-src ${join("'self'", "'unsafe-inline'", res)}`,
    `img-src ${join("'self'", "data:", res)}`,
    `font-src ${join("'self'", "data:", res)}`,
    `media-src ${join("'self'", "data:", res)}`,
    `connect-src ${join("'self'", ...(csp.connectDomains ?? []))}`,
    `frame-src ${csp.frameDomains?.length ? csp.frameDomains.join(" ") : "'none'"}`,
    "object-src 'none'",
    `base-uri ${csp.baseUriDomains?.length ? csp.baseUriDomains.join(" ") : "'self'"}`,
  ].join("; ");
}
