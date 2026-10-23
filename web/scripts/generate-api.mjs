import { spawnSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import openapiTS, { astToString } from "openapi-typescript";

const result = spawnSync("uv", ["run", "python", "scripts/export_openapi.py"], {
  cwd: new URL("../../", import.meta.url),
  encoding: "utf8",
});
if (result.status !== 0)
  throw new Error(
    result.stderr || result.error?.message || "OpenAPI export failed",
  );
const content =
  "// Generated from the application OpenAPI schema. Run npm run generate:api.\n" +
  astToString(await openapiTS(JSON.parse(result.stdout)));
const target = new URL("../src/api/generated.ts", import.meta.url);
if (process.argv.includes("--check")) {
  if ((await readFile(target, "utf8")) !== content)
    throw new Error("OpenAPI types are stale. Run npm run generate:api.");
} else await writeFile(target, content);
