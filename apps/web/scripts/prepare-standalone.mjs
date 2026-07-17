import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const standaloneRoot = join(webRoot, ".next", "standalone", "apps", "web");
const sourceStatic = join(webRoot, ".next", "static");
const targetStatic = join(standaloneRoot, ".next", "static");
const sourcePublic = join(webRoot, "public");
const targetPublic = join(standaloneRoot, "public");

if (!existsSync(join(standaloneRoot, "server.js"))) {
  throw new Error(`Next standalone server was not generated at ${standaloneRoot}`);
}

if (!existsSync(sourceStatic)) {
  throw new Error(`Next static assets were not generated at ${sourceStatic}`);
}

rmSync(targetStatic, { recursive: true, force: true });
mkdirSync(dirname(targetStatic), { recursive: true });
cpSync(sourceStatic, targetStatic, { recursive: true });

if (existsSync(sourcePublic)) {
  rmSync(targetPublic, { recursive: true, force: true });
  cpSync(sourcePublic, targetPublic, { recursive: true });
}

console.log(`Prepared standalone static assets at ${targetStatic}`);
