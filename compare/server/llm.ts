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

export function llmHandler(env: Record<string, string>) {
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
    if (req.method !== "POST") {
      res.statusCode = 405;
      return res.end();
    }
    let body = "";
    for await (const chunk of req) body += chunk;
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
      res.statusCode = 502;
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify({ error: (error as Error).message }));
    }
  };
}
