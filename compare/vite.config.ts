import { readFileSync } from "node:fs";
import { createServer, type RequestListener, type Server } from "node:http";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv, type Plugin } from "vite";
import { buildCsp, parseCsp } from "./server/csp";
import { llmHandler } from "./server/llm";

const SANDBOX_HTML = readFileSync(fileURLToPath(new URL("./server/sandbox.html", import.meta.url)), "utf8");

// The harness needs two origins (MCP Apps sandbox rule) and a server-side LLM
// endpoint, so the dev server grows a sandbox listener and an /api/llm route.
function harness(env: Record<string, string>): Plugin {
  const sandboxPort = Number(env.COMPARE_SANDBOX_PORT || 8081);
  return {
    name: "compare-harness",
    configureServer(server) {
      server.middlewares.use("/api/llm", llmHandler(env));
      server.middlewares.use("/api/config", (_req, res) => {
        res.setHeader("content-type", "application/json");
        res.end(
          JSON.stringify({
            // Scripted: backends on recorded fixtures with a frozen clock.
            scripted: {
              mcpUrl: `http://localhost:${env.SCRIPTED_MCP_APPS_PORT || 3101}/mcp`,
              a2uiUrl: `http://localhost:${env.SCRIPTED_A2UI_AGENT_PORT || 10102}`,
            },
            // Live: backends on the real Open-Meteo API (cached), Gemini on both sides.
            live: {
              mcpUrl: `http://localhost:${env.MCP_APPS_PORT || 3001}/mcp`,
              a2uiUrl: `http://localhost:${env.A2UI_AGENT_PORT || 10002}`,
            },
            sandboxUrl: `http://localhost:${sandboxPort}/sandbox.html`,
            model: env.AGENT_MODEL || "gemini-3.8-flash",
          }),
        );
      });
      // One listener per process: Vite restarts on config changes, so the
      // sandbox server is kept and only its handler is replaced.
      const g = globalThis as { __sandbox?: { server: Server; handle: RequestListener } };
      const handle: RequestListener = (req, res) => {
        const url = new URL(req.url ?? "/", `http://localhost:${sandboxPort}`);
        if (url.pathname !== "/sandbox.html") {
          res.statusCode = 404;
          return res.end();
        }
        res.setHeader("content-type", "text/html; charset=utf-8");
        res.setHeader("content-security-policy", buildCsp(parseCsp(url.searchParams.get("csp"))));
        res.setHeader("cache-control", "no-store");
        res.end(SANDBOX_HTML);
      };
      if (g.__sandbox) g.__sandbox.handle = handle;
      else {
        const state = { handle, server: createServer((req, res) => state.handle(req, res)) };
        state.server.listen(sandboxPort, "127.0.0.1");
        g.__sandbox = state;
      }
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = {
    ...loadEnv(mode, fileURLToPath(new URL("..", import.meta.url)), ""),
    ...process.env,
  } as Record<string, string>;
  return {
    plugins: process.env.VITEST ? [] : [harness(env)],
    server: { port: Number(env.COMPARE_PORT || 8080), strictPort: true, fs: { allow: [".."] } },
  };
});
