import { translator } from "./context";
import { graphEn } from "./graphEn";
import { graphZh } from "./graphZh";

import type { Locale, Translate } from "./context";

const nameKeys = Object.keys(graphEn).filter((key) =>
  key.startsWith("graphCatalog"),
) as (keyof typeof graphEn)[];

export function localizedCatalogName(name: string, t: Translate): string {
  const key = nameKeys.find(
    (key) => graphEn[key] === name || graphZh[key] === name,
  );
  return key ? t(key) : name;
}

export function localizedObjectName(
  kind: string,
  name: string,
  locale: Locale,
  englishName?: string | null,
): string {
  if (
    locale !== "en" ||
    ![
      "source",
      "table",
      "column",
      "metric",
      "dimension",
      "term",
      "owner",
    ].includes(kind)
  )
    return name;
  if (englishName?.trim()) return englishName.trim();
  const t = translator(locale);
  return kind === "column"
    ? name
        .split(".")
        .map((part) => localizedCatalogName(part, t))
        .join(".")
    : localizedCatalogName(name, t);
}
