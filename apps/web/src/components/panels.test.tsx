import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

describe("workbench panels", () => {
  it("keeps a simple smoke invariant", () => {
    expect("ANN (Agentic Neural Network)").toContain("Neural Network");
  });

  it("exposes senior review and production readiness panels", () => {
    const source = readFileSync(join(process.cwd(), "src", "components", "panels.tsx"), "utf-8");

    expect(source).toContain('id: "senior"');
    expect(source).toContain('id: "readiness"');
  });
});
