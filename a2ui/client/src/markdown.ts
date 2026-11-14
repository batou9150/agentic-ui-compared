// Markdown for the basic catalog's Text component: markdown-it, then DOMPurify.
//
// What @a2ui/markdown-it does, inlined: its 0.2.2 release still declares
// `@a2ui/web_core ^0.14` as a peer, which makes npm install a second copy of
// web_core next to the 0.15 one, and two copies break the renderer (a node
// built by one copy is not recognized by the other). It only imports types
// from web_core, so this file replaces it until its peer range moves.
import type { MarkdownRenderer, MarkdownRendererTagClassMap } from "@a2ui/web_core/catalogs/basic/v1";
import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";

const md = new MarkdownIt();

// Apply the renderer's tag -> class map to opening tags, as @a2ui/markdown-it does.
for (const rule of [
  "paragraph_open",
  "heading_open",
  "bullet_list_open",
  "ordered_list_open",
  "list_item_open",
  "link_open",
  "strong_open",
  "em_open",
]) {
  const original = md.renderer.rules[rule];
  md.renderer.rules[rule] = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const classes = (env?.tagClassMap as MarkdownRendererTagClassMap | undefined)?.[token.tag] ?? [];
    for (const name of classes) token.attrJoin("class", name);
    return original ? original(tokens, idx, options, env, self) : self.renderToken(tokens, idx, options);
  };
}

export const renderMarkdown: MarkdownRenderer = async (value, options) =>
  DOMPurify.sanitize(md.render(value, { tagClassMap: options?.tagClassMap }));
