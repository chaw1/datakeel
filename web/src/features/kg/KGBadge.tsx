import { useI18n } from "../../i18n/useI18n";

import { statusLabels } from "./labels";

export function KGBadge({
  value,
}: {
  value?: keyof typeof statusLabels | null;
}) {
  const { t } = useI18n();
  return (
    <span className={`kg-badge ${value ?? "unknown"}`}>
      {t(value ? statusLabels[value] : "kgUnverified")}
    </span>
  );
}
