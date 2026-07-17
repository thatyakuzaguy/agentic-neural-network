import fs from "node:fs";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const ROOT = path.resolve(/* turbopackIgnore: true */ process.env.AEN_ROOT || "D:\\AgenticEngineeringNetwork");
const MAX_PREVIEW_BYTES = 1024 * 1024;
const MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024;
const TEXT_EXTENSIONS = new Set([
  ".css", ".csv", ".diff", ".env", ".example", ".html", ".ini", ".js", ".json",
  ".jsonl", ".jsx", ".log", ".md", ".mjs", ".ps1", ".py", ".sql", ".toml",
  ".ts", ".tsx", ".txt", ".yaml", ".yml",
]);

function safeTarget(relativePath: string) {
  if (!relativePath || path.isAbsolute(relativePath) || relativePath.includes("\0")) {
    throw new Error("A relative path inside the ANN workspace is required.");
  }
  const target = path.resolve(/* turbopackIgnore: true */ ROOT, relativePath);
  if (target !== ROOT && !target.startsWith(`${ROOT}${path.sep}`)) {
    throw new Error("Path traversal outside the ANN workspace is blocked.");
  }
  const realRoot = fs.realpathSync.native(/* turbopackIgnore: true */ ROOT);
  const realTarget = fs.realpathSync.native(/* turbopackIgnore: true */ target);
  if (realTarget !== realRoot && !realTarget.startsWith(`${realRoot}${path.sep}`)) {
    throw new Error("Symlinks outside the ANN workspace are blocked.");
  }
  return { target: realTarget, relative: path.relative(realRoot, realTarget) };
}

function entryFor(parent: string, name: string) {
  const entryPath = path.join(/* turbopackIgnore: true */ parent, name);
  const stat = fs.statSync(entryPath);
  return {
    name,
    path: path.relative(ROOT, entryPath),
    type: stat.isDirectory() ? "directory" : "file",
    size: stat.size,
    modifiedAt: stat.mtime.toISOString(),
  };
}

export async function GET(request: NextRequest) {
  try {
    const requestedPath = request.nextUrl.searchParams.get("path") ?? "";
    const download = request.nextUrl.searchParams.get("download") === "1";
    const { target, relative } = safeTarget(requestedPath);
    const stat = fs.statSync(target);

    if (stat.isDirectory()) {
      if (download) return NextResponse.json({ error: "Directories cannot be downloaded." }, { status: 400 });
      const entries = fs.readdirSync(target)
        .map(name => entryFor(target, name))
        .sort((a, b) => a.type === b.type ? a.name.localeCompare(b.name) : a.type === "directory" ? -1 : 1)
        .slice(0, 300);
      return NextResponse.json({ kind: "directory", path: relative, entries }, { headers: { "Cache-Control": "no-store" } });
    }

    if (download) {
      if (stat.size > MAX_DOWNLOAD_BYTES) {
        return NextResponse.json({ error: "File exceeds the 64 MB desktop download limit." }, { status: 413 });
      }
      return new NextResponse(fs.readFileSync(target), {
        headers: {
          "Cache-Control": "no-store",
          "Content-Disposition": `attachment; filename="${path.basename(target).replaceAll('"', "")}"`,
          "Content-Type": "application/octet-stream",
        },
      });
    }

    const extension = path.extname(target).toLowerCase();
    const previewable = TEXT_EXTENSIONS.has(extension) && stat.size <= MAX_PREVIEW_BYTES;
    return NextResponse.json({
      kind: "file",
      path: relative,
      name: path.basename(target),
      size: stat.size,
      modifiedAt: stat.mtime.toISOString(),
      previewable,
      content: previewable ? fs.readFileSync(target, "utf8") : null,
    }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not read the requested path.";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
