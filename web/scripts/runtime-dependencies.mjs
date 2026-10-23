import { readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { sourceHash } from "./source-hash.mjs";

const assetExtensions = new Set([
  ".css",
  ".less",
  ".sass",
  ".scss",
  ".styl",
  ".stylus",
  ".woff",
  ".woff2",
  ".ttf",
  ".otf",
  ".eot",
  ".svg",
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".avif",
  ".ico",
]);
const viteHelpers = new Set([
  "commonjsHelpers.js",
  "vite/modulepreload-polyfill",
  "vite/modulepreload-polyfill.js",
  "vite/preload-helper.js",
]);

function packageLocation(id, root, locations) {
  const clean = id.replace(/^\0/, "").split("?")[0];
  if (viteHelpers.has(clean)) {
    if (!locations.includes("node_modules/vite"))
      throw new Error("Bundled Vite helper is missing from package-lock.json");
    return "node_modules/vite";
  }
  const relative = path
    .relative(root, path.resolve(root, clean))
    .split(path.sep)
    .join("/");
  if (!relative.split("/").includes("node_modules")) return null;
  if (relative.startsWith("../"))
    throw new Error("Bundled dependency is outside the npm lock root");
  const parts = relative.split("/");
  const moduleIndex = parts.lastIndexOf("node_modules");
  const packageEnd =
    moduleIndex + (parts[moduleIndex + 1]?.startsWith("@") ? 3 : 2);
  const location = parts.slice(0, packageEnd).join("/");
  if (!locations.includes(location))
    throw new Error(`Bundled dependency is missing from npm lock: ${relative}`);
  return location;
}

export function runtimeDependencies() {
  let root;
  return {
    name: "runtime-dependency-inventory",
    apply: "build",
    enforce: "post",
    configResolved(config) {
      root = config.root;
    },
    async generateBundle(_options, bundle) {
      const lock = JSON.parse(
        await readFile(path.join(root, "package-lock.json"), "utf8"),
      );
      const locations = Object.keys(lock.packages).filter((location) =>
        location.startsWith("node_modules/"),
      );
      const included = [...this.getModuleIds()].filter(
        (id) => this.getModuleInfo(id)?.isIncluded,
      );
      for (const output of Object.values(bundle)) {
        included.push(
          ...(output.type === "chunk"
            ? Object.keys(output.modules)
            : output.originalFileNames),
        );
      }
      // CSS imports and inlined assets bypass Rollup's module graph. Only their
      // watched source types count; build-tool/configuration watch files do not.
      included.push(
        ...this.getWatchFiles().filter((id) =>
          assetExtensions.has(path.extname(id).toLowerCase()),
        ),
      );
      const packages = [
        ...new Set(
          included
            .map((id) => packageLocation(id, root, locations))
            .filter((location) => location !== null),
        ),
      ].sort();
      this.emitFile({
        type: "asset",
        fileName: ".runtime-dependencies.json",
        source: `${JSON.stringify(
          {
            schema_version: 1,
            source_hash: (await sourceHash(pathToFileURL(`${root}/`))).trim(),
            packages,
          },
          null,
          2,
        )}\n`,
      });
    },
  };
}
