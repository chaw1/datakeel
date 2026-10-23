import { writeFile } from "node:fs/promises";

import { sourceHash } from "./source-hash.mjs";

await writeFile(
  new URL("../../datakeel/web_dist/.source-hash", import.meta.url),
  await sourceHash(),
);
