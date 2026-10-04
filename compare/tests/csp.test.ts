import { describe, expect, it } from "vitest";
import { buildCsp, parseCsp } from "../server/csp";

describe("view CSP", () => {
  it("is strict by default", () => {
    const csp = buildCsp(parseCsp(null));
    expect(csp).toContain("default-src 'none'");
    expect(csp).toContain("connect-src 'self'");
    expect(csp).toContain("frame-src 'none'");
  });

  it("adds declared origins and drops anything that is not an origin", () => {
    const csp = buildCsp(
      parseCsp(
        JSON.stringify({
          connectDomains: ["https://api.example.com", "x; script-src *"],
          resourceDomains: ["https://*.cdn.example"],
        }),
      ),
    );
    expect(csp).toContain("connect-src 'self' https://api.example.com");
    expect(csp).toContain("script-src 'self' 'unsafe-inline' https://*.cdn.example");
    expect(csp).not.toContain("x; script-src *");
  });
});
