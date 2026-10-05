// POST /api/llm: one Gemini generateContent call for the MCP Apps host's agent
// loop (Live mode). Runs in the dev server so credentials never reach the
// browser. Same model ID as the A2UI agent (AGENT_MODEL).
import { GoogleGenAI, type Content, type FunctionDeclaration } from "@google/genai";
import type { IncomingMessage, ServerResponse } from "node:http";

export interface LlmRequest {
  system: string;
  contents: Content[];
  functions: FunctionDeclaration[];
}

const MAX_BODY = 1_000_000; // a long Live conversation stays well under 1 MB

function fail(res: ServerResponse, status: number, error: string): void {
  res.statusCode = status;
  res.setHeader("content-type", "application/json");
  res.end(JSON.stringify({ error }));
}

export function llmHandler(env: Record<string, string>) {
  // Only the harness page may spend the Gemini quota. Requiring JSON forces a
  // CORS preflight for any other site, and the Origin check refuses it.
  const allowedOrigins = new Set(
    [env.COMPARE_PORT || "8080"].flatMap((port) => [`http://localhost:${port}`, `http://127.0.0.1:${port}`]),
  );
  let ai: GoogleGenAI | undefined;
  const model = env.AGENT_MODEL || "gemini-3.8-flash";
  const client = () =>
    (ai ??=
      env.GOOGLE_GENAI_USE_VERTEXAI?.toLowerCase() === "false"
        ? new GoogleGenAI({ apiKey: env.GEMINI_API_KEY })
        : new GoogleGenAI({
            vertexai: true,
            project: env.GOOGLE_CLOUD_PROJECT,
            location: env.GOOGLE_CLOUD_LOCATION || "global",
          }));

  return async (req: IncomingMessage, res: ServerResponse) => {
    if (req.method !== "POST") return fail(res, 405, "Method not allowed.");
    if (!allowedOrigins.has(req.headers.origin ?? "")) return fail(res, 403, "Forbidden origin.");
    if (!req.headers["content-type"]?.startsWith("application/json"))
      return fail(res, 415, "Expected application/json.");
    let body = "";
    for await (const chunk of req) {
      body += chunk;
      if (body.length > MAX_BODY) return fail(res, 413, "Request body too large.");
    }
    try {
      const { system, contents, functions } = JSON.parse(body) as LlmRequest;
      const response = await client().models.generateContent({
        model,
        contents,
        config: { systemInstruction: system, tools: [{ functionDeclarations: functions }] },
      });
      res.setHeader("content-type", "application/json");
      res.end(
        JSON.stringify({
          model,
          content: response.candidates?.[0]?.content ?? { role: "model", parts: [] },
          usage: response.usageMetadata ?? {},
        }),
      );
    } catch (error) {
      // The SDK error can carry project or quota details: log it, keep it off the page.
      console.error("[api/llm]", error);
      fail(res, 502, "The LLM call failed; see the dev server log.");
    }
  };
}
