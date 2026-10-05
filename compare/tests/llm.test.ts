import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { llmHandler } from "../server/llm";

// Only the guards are tested: every request here is refused before Gemini.
describe("/api/llm guards", () => {
  let server: Server;
  let url: string;

  beforeAll(async () => {
    server = createServer(llmHandler({ COMPARE_PORT: "8080" }));
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    url = `http://127.0.0.1:${(server.address() as AddressInfo).port}/`;
  });
  afterAll(() => new Promise<void>((resolve) => server.close(() => resolve())));

  const post = (headers: Record<string, string>, body = "{}") =>
    fetch(url, { method: "POST", headers, body });
  const harness = { origin: "http://localhost:8080", "content-type": "application/json" };

  it("refuses other origins", async () => {
    expect((await post({ ...harness, origin: "https://evil.example" })).status).toBe(403);
    expect((await post({ ...harness, origin: "http://localhost:9999" })).status).toBe(403);
  });

  it("refuses non-JSON bodies (the CORS simple-request path)", async () => {
    expect((await post({ ...harness, "content-type": "text/plain" })).status).toBe(415);
  });

  it("refuses oversized bodies", async () => {
    expect((await post(harness, "x".repeat(1_100_000))).status).toBe(413);
  });

  it("refuses other methods", async () => {
    expect((await fetch(url, { headers: harness })).status).toBe(405);
  });
});
