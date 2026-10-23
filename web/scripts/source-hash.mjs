import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

async function sourceFiles(directory, prefix) {
  const entries = await readdir(directory, { withFileTypes: true });
  const groups = await Promise.all(
    entries.map(async (entry) => {
      const relative = `${prefix}${entry.name}`;
      if (entry.isDirectory())
        return sourceFiles(
          new URL(`${entry.name}/`, directory),
          `${relative}/`,
        );
      if (!entry.isFile())
        throw new Error(`Unsupported source entry: ${relative}`);
      return [relative];
    }),
  );
  return groups.flat();
}

export async function sourceHash(root = new URL("../", import.meta.url)) {
  const paths = [
    ...(await sourceFiles(new URL("src/", root), "src/")),
    "package-lock.json",
  ].sort();
  const hash = createHash("sha256");
  for (const path of paths) {
    const contents = await readFile(fileURLToPath(new URL(path, root)));
    hash.update(`${path}\0${String(contents.byteLength)}\0`);
    hash.update(contents);
    hash.update("\0");
  }
  return `${hash.digest("hex")}\n`;
}
