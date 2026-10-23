import { useEffect, useState } from "react";

import { I18nContext, translator } from "./context";

import type { Locale } from "./context";
import type { ReactNode } from "react";

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(() =>
    localStorage.getItem("datakeel.locale") === "zh" ? "zh" : "en",
  );
  useEffect(() => {
    localStorage.setItem("datakeel.locale", locale);
    document.documentElement.lang = locale;
  }, [locale]);
  return (
    <I18nContext.Provider value={{ locale, setLocale, t: translator(locale) }}>
      {children}
    </I18nContext.Provider>
  );
}
