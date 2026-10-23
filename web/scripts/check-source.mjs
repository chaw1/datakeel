import { readFile } from "node:fs/promises";

import { sourceHash } from "./source-hash.mjs";

const recorded = await readFile(
  new URL("../../datakeel/web_dist/.source-hash", import.meta.url),
  "utf8",
);
const current = await sourceHash();
if (recorded !== current)
  throw new Error(
    "Frontend source changed: run npm run build before committing.",
  );
const inventory = JSON.parse(
  await readFile(
    new URL(
      "../../datakeel/web_dist/.runtime-dependencies.json",
      import.meta.url,
    ),
    "utf8",
  ),
);
if (inventory.source_hash !== current.trim())
  throw new Error(
    "Bundled dependency inventory changed: run npm run build before committing.",
  );
