// Shared plumbing for the three views: App connection, host theming, helpers.
import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";
import type { CallToolResult } from "@modelcontextprotocol/client";
import type { Attribution, Payload, Place } from "./types";
import "./base.css";

export function createApp(name: string, onThemeChange?: () => void): App {
  const app = new App({ name, version: "0.1.0" });
  app.onhostcontextchanged = (ctx) => {
    applyHostContext(ctx);
    onThemeChange?.();
  };
  app.onerror = console.error;
  return app;
}

export async function connect(app: App): Promise<void> {
  await app.connect();
  const ctx = app.getHostContext();
  if (ctx) applyHostContext(ctx);
}

// The host owns the look: theme, CSS variables and fonts come from it.
function applyHostContext(ctx: McpUiHostContext): void {
  if (ctx.theme) applyDocumentTheme(ctx.theme);
  if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
  if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);
}

export function payloadOf<T extends Payload>(result: CallToolResult): T | null {
  return (result.structuredContent as T | undefined) ?? null;
}

export function errorText(result: CallToolResult): string {
  const first = result.content?.[0];
  return first && first.type === "text" ? first.text : "Something went wrong.";
}

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string> = {},
  ...children: (Node | string | null)[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const child of children) if (child !== null) node.append(child);
  return node;
}

export function placeLabel(p: Place): string {
  return [p.name, p.region, p.country].filter((v, i, a) => v && a.indexOf(v) === i).join(", ");
}

export function attributionEl(a?: Attribution): HTMLElement {
  const text = a?.text ?? "Weather data by Open-Meteo.com";
  return el(
    "footer",
    { class: "attribution", "data-testid": "attribution" },
    el("a", { href: a?.url ?? "https://open-meteo.com/", target: "_blank", rel: "noopener" }, text),
    ` (${a?.license ?? "CC BY 4.0"})`,
  );
}

export function showError(root: HTMLElement, message: string): void {
  root.replaceChildren(el("p", { class: "error", "data-testid": "view-error" }, message));
}

export function showLoading(root: HTMLElement): void {
  root.replaceChildren(el("p", { class: "muted", "data-testid": "view-loading" }, "Loading…"));
}

export function cssVar(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}
