import fs from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const ROOT = process.env.AEN_ROOT || "D:\\AgenticEngineeringNetwork";

function rootPath(...segments: string[]) {
  return path.join(/*turbopackIgnore: true*/ ROOT, ...segments);
}

function safeReadDir(relativePath: string) {
  const fullPath = rootPath(relativePath);
  try {
    return fs
      .readdirSync(fullPath, { withFileTypes: true })
      .map((entry) => {
        const entryPath = path.join(/*turbopackIgnore: true*/ fullPath, entry.name);
        const stat = fs.statSync(entryPath);
        return {
          name: entry.name,
          path: path.relative(/*turbopackIgnore: true*/ ROOT, entryPath),
          type: entry.isDirectory() ? "directory" : "file",
          size: stat.size,
          modifiedAt: stat.mtime.toISOString(),
        };
      })
      .sort((a, b) => b.modifiedAt.localeCompare(a.modifiedAt))
      .slice(0, 80);
  } catch {
    return [];
  }
}

function readDeclaredModels() {
  const inventoryPath = rootPath("config", "ann_model_inventory.json");
  try {
    const stat = fs.statSync(inventoryPath);
    const payload = JSON.parse(fs.readFileSync(inventoryPath, "utf8")) as {
      models?: Array<Record<string, unknown>>;
    };
    const declared = Array.isArray(payload.models) ? payload.models : [];
    return declared.map((model, index) => {
      const sourcePath = String(model.source_path ?? model.path ?? "");
      const modelName = String(model.name ?? model.model_name ?? `model-${index + 1}`);
      const estimatedVramMb = Number(model.estimated_vram_mb ?? 0);
      let modifiedAt = stat.mtime.toISOString();
      let size = Number.isFinite(estimatedVramMb) && estimatedVramMb > 0 ? estimatedVramMb * 1024 * 1024 : 0;

      try {
        const modelStat = fs.statSync(sourcePath);
        modifiedAt = modelStat.mtime.toISOString();
        if (modelStat.isFile()) size = modelStat.size;
      } catch {
        // Inventory paths may point outside the app root or to offline drives; keep declared metadata visible.
      }

      return {
        name: modelName,
        path: sourcePath || modelName,
        type: "file" as const,
        size,
        modifiedAt,
      };
    });
  } catch {
    return safeReadDir("models");
  }
}

function readAuditLogs() {
  const auditPath = rootPath("logs", "audit.jsonl");
  try {
    return fs
      .readFileSync(auditPath, "utf8")
      .split(/\r?\n/)
      .filter(Boolean)
      .slice(-80)
      .reverse()
      .map((line) => {
        try {
          const parsed = JSON.parse(line) as Record<string, unknown>;
          return {
            level: "INFO",
            time: String(parsed.timestamp ?? parsed.time ?? ""),
            agent: String(parsed.actor ?? parsed.agent ?? parsed.component ?? "ANN"),
            msg: String(parsed.message ?? parsed.event ?? line),
          };
        } catch {
          return { level: "INFO", time: "", agent: "ANN", msg: line };
        }
      });
  } catch {
    return [];
  }
}

export async function GET() {
  const generatedProjects = safeReadDir("generated-projects");
  const outputArtifacts = safeReadDir("outputs");
  const projectRuns = safeReadDir("project_runs");
  const docs = safeReadDir("docs");
  const models = readDeclaredModels();
  const logs = readAuditLogs();

  return NextResponse.json(
    {
      root: ROOT,
      sampledAt: new Date().toISOString(),
      projects: [...generatedProjects, ...projectRuns],
      artifacts: outputArtifacts,
      docs,
      models,
      logs,
      settings: {
        approvalMode: "supervised",
        workspaceRoot: ROOT,
        terminalMode: "safe-allowlist",
        network: "disabled-by-default",
      },
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
