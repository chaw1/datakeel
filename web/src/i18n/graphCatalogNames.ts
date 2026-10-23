import { graphEn } from "./graphEn";
import { graphZh } from "./graphZh";

import type { Translate } from "./context";

const nameKeys = Object.keys(graphEn).filter((key) =>
  key.startsWith("graphCatalog"),
) as (keyof typeof graphEn)[];

export function localizedCatalogName(name: string, t: Translate): string {
  const key = nameKeys.find(
    (key) => graphEn[key] === name || graphZh[key] === name,
  );
  return key ? t(key) : name;
}
