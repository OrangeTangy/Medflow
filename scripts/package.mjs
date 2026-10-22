import { readFile, writeFile, mkdir, readdir, cp } from "node:fs/promises";
import { join, extname } from "node:path";
import { build } from "esbuild";
const assets = {};
const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json",
  ".webmanifest": "application/manifest+json",
  ".txt": "text/plain",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};
async function walk(dir, prefix = "") {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, e.name),
      key = prefix + "/" + e.name;
    if (e.isDirectory()) await walk(path, key);
    else
      assets[key] = {
        body: (await readFile(path)).toString("base64"),
        type: mime[extname(e.name)] || "application/octet-stream",
      };
  }
}
await walk("out");
await writeFile(
  "worker/assets.mjs",
  "export const assets=" + JSON.stringify(assets) + ";",
);
await mkdir("dist/server", { recursive: true });
await mkdir("dist/.openai", { recursive: true });
await build({
  entryPoints: ["worker/index.mjs"],
  bundle: true,
  format: "esm",
  platform: "browser",
  target: "es2022",
  outfile: "dist/server/index.js",
  minify: true,
});
await cp(".openai/hosting.json", "dist/.openai/hosting.json");
await cp("drizzle", "dist/drizzle", { recursive: true });
console.log(
  "Packaged Next.js application and sandbox API as a Worker ESM artifact.",
);
