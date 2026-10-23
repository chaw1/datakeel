import { createContext } from "react";

import { en } from "./en";
import { zh } from "./zh";

import type { MessageKey } from "./en";

export type Locale = "en" | "zh";
export type Translate = (
  key: MessageKey,
  values?: Record<string, string | number>,
) => string;
export function translator(locale: Locale): Translate {
  const plurals = new Intl.PluralRules(locale);
  return (key, values = {}) => {
    const message = (locale === "zh" ? zh : en)[key].replace(
      /\{(\w+), plural, one \{([^{}]*)\} other \{([^{}]*)\}\}/g,
      (_match: string, name: string, one: string, other: string) =>
        plurals.select(Number(values[name] ?? 0)) === "one" ? one : other,
    );
    return Object.entries(values).reduce(
      (message, [name, value]) =>
        message.replaceAll(`{${name}}`, String(value)),
      message,
    );
  };
}
export const I18nContext = createContext<{
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Translate;
}>({
  locale: "en",
  setLocale: () => undefined,
  t: translator("en"),
});
