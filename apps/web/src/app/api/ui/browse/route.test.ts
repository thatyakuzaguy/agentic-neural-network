import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { GET } from "./route";

describe("ANN read-only UI browser", () => {
  it("previews a text file inside the ANN workspace", async () => {
    const request = new NextRequest("http://localhost/api/ui/browse?path=README.md");

    const response = await GET(request);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.kind).toBe("file");
    expect(payload.path).toBe("README.md");
    expect(payload.previewable).toBe(true);
    expect(payload.content).toContain("Agentic Engineering Network");
  });

  it("blocks path traversal outside the ANN workspace", async () => {
    const request = new NextRequest("http://localhost/api/ui/browse?path=..%5C..%5CWindows%5Cwin.ini");

    const response = await GET(request);
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload.error).toContain("blocked");
  });
});
