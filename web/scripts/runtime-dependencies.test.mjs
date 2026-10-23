import { execFileSync } from "node:child_process";
import {
  mkdtemp,
  mkdir,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { afterEach, expect, it } from "vitest";

import { sourceHash } from "./source-hash.mjs";

const directories = [];
const web = process.cwd();
const plugin = pathToFileURL(
  path.join(web, "scripts/runtime-dependencies.mjs"),
).href;
const locations = [
  "node_modules/dev-runtime",
  "node_modules/dev-runtime/node_modules/@fixture/child",
  "node_modules/font-kit",
  "node_modules/theme-kit",
  "node_modules/vite",
];

afterEach(async () => {
  await Promise.all(
    directories.splice(0).map((root) => rm(root, { recursive: true })),
  );
});

async function put(root, name, content) {
  const target = path.join(root, name);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, content);
}

async function fixture() {
  const root = await realpath(
    await mkdtemp(path.join(tmpdir(), "runtime-inventory-")),
  );
  directories.push(root);
  const packages = { "": { devDependencies: { "dev-runtime": "1.0.0" } } };
  for (const location of [...locations, "node_modules/unused-tool"]) {
    const manifest = {
      name: location.split("node_modules/").at(-1),
      version: "1.0.0",
      type: "module",
      main: "index.js",
    };
    packages[location] = { ...manifest, dev: true };
    await put(root, `${location}/package.json`, JSON.stringify(manifest));
  }
  await put(root, "package.json", JSON.stringify({ type: "module" }));
  await put(
    root,
    "package-lock.json",
    JSON.stringify({ lockfileVersion: 3, packages }),
  );
  await put(
    root,
    "index.html",
    '<script type="module" src="/src/main.js"></script>',
  );
  await put(
    root,
    "src/main.js",
    'import { value } from "dev-runtime"; import "./style.css"; document.body.dataset.value = value;',
  );
  await put(
    root,
    "src/style.css",
    '@import "theme-kit/theme.css"; @import "font-kit/font.css";',
  );
  await put(
    root,
    "node_modules/dev-runtime/index.js",
    'import { value as child } from "@fixture/child"; export const value = `runtime:${child}`;',
  );
  await put(
    root,
    "node_modules/dev-runtime/node_modules/@fixture/child/index.js",
    'export const value = "bundled dev dependency";',
  );
  await put(
    root,
    "node_modules/theme-kit/theme.css",
    "body { color: #123456; }",
  );
  await put(
    root,
    "node_modules/font-kit/font.css",
    '@font-face { font-family: Fixture; src: url("./font.woff2") format("woff2"); }',
  );
  await put(
    root,
    "node_modules/font-kit/font.woff2",
    new Uint8Array([119, 79, 70, 50]),
  );
  await put(
    root,
    "node_modules/unused-tool/index.js",
    "export default 'build-only';",
  );
  return root;
}

function build(root, assetsInlineLimit = 0, modulePreload = true) {
  const script = `
    import path from "node:path";
    import { build } from "vite";
    import { runtimeDependencies } from ${JSON.stringify(plugin)};
    const root = process.argv[1];
    const result = await build({ root, configFile: false, logLevel: "silent",
      plugins: [runtimeDependencies(), { name: "build-only-input", buildStart() {
        this.addWatchFile(path.join(root, "node_modules/unused-tool/index.js"));
      } }], build: { write: false, assetsInlineLimit: Number(process.argv[2]), modulePreload: process.argv[3] !== "false" } });
    const inventory = result.output.find((asset) => asset.fileName === ".runtime-dependencies.json");
    process.stdout.write(inventory.source);
  `;
  return JSON.parse(
    execFileSync(
      process.execPath,
      [
        "--input-type=module",
        "-e",
        script,
        root,
        String(assetsInlineLimit),
        String(modulePreload),
      ],
      { cwd: web, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    ),
  );
}

it.each([0, 4096])(
  "audits dev imports, CSS/font assets and helpers with inline limit %i",
  async (assetsInlineLimit) => {
    const root = await fixture();
    const inventory = build(root, assetsInlineLimit);
    expect(inventory).toEqual({
      schema_version: 1,
      source_hash: (await sourceHash(pathToFileURL(`${root}/`))).trim(),
      packages: locations,
    });
    expect(JSON.stringify(inventory)).not.toContain(root);
    expect(build(root, assetsInlineLimit)).toEqual(inventory);
  },
);

it.each([
  "node_modules/font-kit",
  "node_modules/dev-runtime/node_modules/@fixture/child",
])(
  "rejects bundled package %s without its own npm lock entry",
  async (location) => {
    const root = await fixture();
    const filename = path.join(root, "package-lock.json");
    const lock = JSON.parse(await readFile(filename, "utf8"));
    lock.packages = Object.fromEntries(
      Object.entries(lock.packages).filter(([key]) => key !== location),
    );
    await writeFile(filename, JSON.stringify(lock));
    expect(() => build(root)).toThrow(
      /Bundled dependency is missing from npm lock/,
    );
  },
);

it("attributes injected CommonJS interop when the preload helper is disabled", async () => {
  const root = await fixture();
  await put(
    root,
    "node_modules/dev-runtime/package.json",
    JSON.stringify({
      name: "dev-runtime",
      version: "1.0.0",
      main: "index.js",
      type: "commonjs",
    }),
  );
  await put(
    root,
    "node_modules/dev-runtime/index.js",
    'module.exports = "CommonJS runtime";',
  );
  await put(
    root,
    "src/main.js",
    'import value from "dev-runtime"; document.body.dataset.value = value;',
  );
  expect(build(root, 0, false).packages).toEqual([
    "node_modules/dev-runtime",
    "node_modules/vite",
  ]);
});
