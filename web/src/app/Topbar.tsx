import { CommandPalette } from "../components/CommandPalette";
import { Select } from "../components/ui";
import { useI18n } from "../i18n/useI18n";

import { ActorBadge } from "./ActorBadge";
import { Breadcrumbs } from "./Breadcrumbs";
import { PaletteControl } from "./PaletteControl";
import { ThemeControl } from "./ThemeControl";

import type { Page } from "./navigation";
import type { ActorIdentity } from "./useActorIdentity";
import type { Dataset } from "../api/types";
import type { ObjectKind, ObjectTab } from "../features/object/navigation";

export function Topbar({
  page,
  navigate,
  selected,
  objectName,
  objectKind,
  objectTab,
  params,
  identity,
}: {
  page: Page;
  navigate: (page: Page) => void;
  selected?: Dataset;
  objectName?: string;
  objectKind?: ObjectKind;
  objectTab?: ObjectTab;
  params?: URLSearchParams;
  identity?: ActorIdentity;
}) {
  const { t, locale, setLocale } = useI18n();
  return (
    <header className="topbar">
      <Breadcrumbs
        page={page}
        navigate={navigate}
        selected={selected}
        objectName={objectName}
        objectKind={objectKind}
        objectTab={objectTab}
        params={params}
      />
      <div className="topbar-right">
        <CommandPalette />
        <ActorBadge identity={identity} />
        <PaletteControl />
        <ThemeControl />
        <Select
          size="sm"
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
        </Select>
      </div>
    </header>
  );
}
