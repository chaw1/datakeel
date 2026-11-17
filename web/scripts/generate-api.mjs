import { spawnSync } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import openapiTS, { astToString } from "openapi-typescript";
import { format } from "prettier";

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

const declarations = spawnSync(
  "uv",
  ["run", "python", "scripts/export_action_declarations.py"],
  {
    cwd: new URL("../../", import.meta.url),
    encoding: "utf8",
  },
);
if (declarations.status !== 0)
  throw new Error(declarations.stderr || "Action declaration export failed");
const declarationContent = await format(
  "// Generated from active action declarations.\n" +
    'export const actionDeclarations: Readonly<Partial<Record<string, { phrases: Readonly<Record<string, readonly string[]>>; widget: "generic"; titles: Readonly<Record<string, string>> }>>> = ' +
    JSON.stringify(JSON.parse(declarations.stdout)) +
    ";\n",
  { parser: "typescript" },
);
const declarationTarget = new URL(
  "../src/api/actionDeclarations.ts",
  import.meta.url,
);
if (process.argv.includes("--check")) {
  if ((await readFile(declarationTarget, "utf8")) !== declarationContent)
    throw new Error("Action declarations are stale");
} else await writeFile(declarationTarget, declarationContent);
