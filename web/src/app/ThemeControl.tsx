import { useEffect, useState } from "react";

import { useI18n } from "../i18n/useI18n";

type Theme = "system" | "light" | "dark";

export function ThemeControl() {
  const { t } = useI18n();
  const [theme, setTheme] = useState<Theme>(() => {
    const saved =
      localStorage.getItem("dk-theme") ??
      localStorage.getItem("datakeel.theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  });
  useEffect(() => {
    localStorage.setItem("dk-theme", theme);
    localStorage.setItem("datakeel.theme", theme);
    if (theme === "system")
      document.documentElement.removeAttribute("data-theme");
    else document.documentElement.dataset.theme = theme;
  }, [theme]);
  return (
    <select
      aria-label={t("theme")}
      value={theme}
      onBlur={(event) => {
        const value = event.target.value;
        setTheme(value === "dark" || value === "light" ? value : "system");
      }}
      onChange={(event) => {
        const value = event.target.value;
        setTheme(value === "dark" || value === "light" ? value : "system");
      }}
    >
      <option value="system">{t("themeSystem")}</option>
      <option value="light">{t("themeLight")}</option>
      <option value="dark">{t("themeDark")}</option>
    </select>
  );
}
