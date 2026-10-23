import { copyFile, mkdir } from "node:fs/promises";

const output = new URL("../../datakeel/web_dist/", import.meta.url);
for (const name of ["lineage", "report", "tasks", "action-runs"]) {
  const directory = new URL(`${name}/`, output);
  await mkdir(directory, { recursive: true });
  await copyFile(
    new URL("index.html", output),
    new URL("index.html", directory),
  );
}
