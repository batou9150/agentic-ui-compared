// Live mode for the MCP Apps pane: a small agent loop, standing in for the
// LLM a real MCP host would bring. Same Gemini model as the A2UI agent.
// The model sees each tool's text `content`; views get `structuredContent`.
import type { McpHost } from "./host";

interface Part {
  text?: string;
  functionCall?: { id?: string; name: string; args?: Record<string, unknown> };
  functionResponse?: { id?: string; name: string; response: Record<string, unknown> };
}
interface Content {
  role: "user" | "model";
  parts: Part[];
}
interface LlmReply {
  content: Content;
  usage: { promptTokenCount?: number; candidatesTokenCount?: number };
  error?: string;
}

export const SYSTEM = `You are a concise assistant for weather, forecasts and local time in cities.
Use the tools; never guess weather data. Tools with a view render their own UI:
after calling one, answer with ONE short sentence and do not repeat the numbers.
If a city is ambiguous the view shows a picker; tell the user to pick one.`;

const MAX_STEPS = 6;

export interface AgentHooks {
  text(text: string): void;
  usage(calls: number, input: number, output: number): void;
}

export class McpAgent {
  private history: Content[] = [];
  private notes: string[] = [];

  constructor(
    private readonly host: McpHost,
    private readonly hooks: AgentHooks,
  ) {}

  /** What a view reported with ui/update-model-context, for the next turn. */
  addModelContext(text: string): void {
    this.notes.push(text);
  }

  reset(): void {
    this.history = [];
    this.notes = [];
  }

  async ask(prompt: string, container: HTMLElement): Promise<void> {
    const notes = this.notes.splice(0).map((n) => `[UI context] ${n}`);
    this.history.push({ role: "user", parts: [{ text: [...notes, prompt].join("\n") }] });
    const functions = this.host.modelTools.map((t) => ({
      name: t.name,
      description: t.description ?? t.title ?? t.name,
      parametersJsonSchema: t.inputSchema,
    }));
    for (let step = 0; step < MAX_STEPS; step++) {
      const response = await fetch("/api/llm", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ system: SYSTEM, contents: this.history, functions }),
      });
      const reply = (await response.json()) as LlmReply;
      if (!response.ok) throw new Error(reply.error ?? `LLM call failed (${response.status})`);
      this.hooks.usage(1, reply.usage.promptTokenCount ?? 0, reply.usage.candidatesTokenCount ?? 0);
      this.history.push(reply.content);
      const calls = reply.content.parts.filter((p) => p.functionCall).map((p) => p.functionCall!);
      const text = reply.content.parts
        .map((p) => p.text ?? "")
        .join("")
        .trim();
      if (text) this.hooks.text(text);
      if (calls.length === 0) return;
      const responses: Part[] = [];
      for (const call of calls) {
        const result = await this.host.callTool(call.name, call.args ?? {}, container);
        const content = (result.content ?? []).map((c) => (c.type === "text" ? c.text : "")).join("\n");
        responses.push({
          functionResponse: {
            id: call.id,
            name: call.name,
            response: { content, isError: !!result.isError },
          },
        });
      }
      this.history.push({ role: "user", parts: responses });
    }
    this.hooks.text("(Stopped after too many tool calls.)");
  }
}
