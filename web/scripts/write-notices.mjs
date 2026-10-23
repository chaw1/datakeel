import assert from "node:assert/strict";
import { readFile, readdir, writeFile, mkdir } from "node:fs/promises";

const outputDirectory = new URL("../../datakeel/web_dist/", import.meta.url);
const inventory = JSON.parse(
  await readFile(
    new URL(".runtime-dependencies.json", outputDirectory),
    "utf8",
  ),
);
assert.equal(inventory.schema_version, 1);
assert.ok(Array.isArray(inventory.packages));
const locations = [...new Set(inventory.packages)].sort();
const notices = await Promise.all(
  locations.map(async (location) => {
    assert.equal(typeof location, "string");
    assert.match(
      location,
      /^node_modules\/(?:@[^/.]+\/)?[^/.][^/]*(?:\/node_modules\/(?:@[^/.]+\/)?[^/.][^/]*)*$/,
    );
    const root = new URL(`../${location}/`, import.meta.url);
    const manifest = JSON.parse(
      await readFile(new URL("package.json", root), "utf8"),
    );
    const filename = (await readdir(root))
      .sort()
      .find((name) => /^(?:licen[cs]e|copying)(?:\.(?:md|txt))?$/i.test(name));
    assert.ok(filename, `Missing upstream license: ${location}`);
    let license = await readFile(new URL(filename, root), "utf8");
    if (manifest.name === "vite") {
      // The browser includes Vite runtime helpers and the CommonJS interop helper.
      assert.equal(manifest.license, "MIT");
      const boundary = "# Licenses of bundled dependencies";
      assert.ok(license.startsWith("# Vite core license"));
      assert.ok(license.includes(boundary));
      const commonJsNotice = license
        .split("\n---------------------------------------\n")
        .find((section) =>
          section.includes("## @rollup/plugin-alias, @rollup/plugin-commonjs,"),
        );
      assert.ok(commonJsNotice?.includes("The MIT License (MIT)"));
      license = `${license.split(boundary)[0].trimEnd()}\n\n${commonJsNotice.trim()}`;
    }
    license = license
      .split("\n")
      .map((line) => line.trimEnd())
      .join("\n");
    return `${manifest.name} ${manifest.version}\n${"=".repeat(60)}\n\n${license}`;
  }),
);
const publicDirectory = new URL("../public/", import.meta.url);
await mkdir(publicDirectory, { recursive: true });
const content = `Datakeel web runtime license notices\n\n${notices.join("\n\n")}\n`;
for (const directory of [publicDirectory, outputDirectory])
  await writeFile(new URL("THIRD-PARTY-LICENSES.txt", directory), content);
