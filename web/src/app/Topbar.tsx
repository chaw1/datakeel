import { CommandPalette } from "../components/CommandPalette";
import { Icon } from "../components/Icon";
import { localizedObjectName } from "../i18n/graphCatalogNames";
import { useI18n } from "../i18n/useI18n";

import { operationPages } from "./navigation";
import { ThemeControl } from "./ThemeControl";

import type { Page } from "./navigation";
import type { Dataset } from "../api/types";
import type { ObjectKind } from "../features/object/navigation";

export function Topbar({
  page,
  navigate,
  selected,
  objectName,
  objectKind,
}: {
  page: Page;
  navigate: (page: Page) => void;
  selected?: Dataset;
  objectName?: string;
  objectKind?: ObjectKind;
}) {
  const { t, locale, setLocale } = useI18n();
  const operation = operationPages.find((item) => item.id === page);
  const label = operation
    ? t(operation.label)
    : page === "workbench"
      ? t("workbench")
      : page === "labeling"
        ? t("wbNav")
        : page === "object"
          ? locale === "en" && objectName && objectKind
            ? localizedObjectName(objectKind, objectName, locale)
            : t("pageObject")
          : page === "runs"
            ? t("runRecords")
            : page === "quality" || page === "quality-rules"
              ? t(page === "quality" ? "dataQuality" : "dqNav")
              : page === "datasets"
                ? t("dataLibraryLabel")
                : (selected?.name ?? t("workspaceLabel"));
  return (
    <header className="topbar">
      <div className="breadcrumb">
        <button
          onClick={() => {
            navigate("workbench");
          }}
        >
          {t("workspaceLabel")}
        </button>
        <Icon name="chevron" size={12} />
        <span className="breadcrumb-current">{label}</span>
      </div>
      <div className="topbar-right">
        <CommandPalette />
        <ThemeControl />
        <select
          aria-label={t("language")}
          value={locale}
          onBlur={(event) => {
            setLocale(event.target.value === "zh" ? "zh" : "en");
          }}
          onChange={(event) => {
            setLocale(event.target.value === "zh" ? "zh" : "en");
          }}
        >
          <option value="en">{t("english")}</option>
          <option value="zh">{t("chinese")}</option>
        </select>
      </div>
    </header>
  );
}
