import { useI18n } from "../../i18n/useI18n";

import type { Quality as QualityData } from "../../api/types";
export function QualityScore({
  quality,
  small = false,
}: {
  quality: QualityData | null;
  small?: boolean;
}) {
  const { t } = useI18n();

  const total = quality?.total ?? 0;
  return (
    <div
      className={`score-ring ${small ? "small-ring" : ""}`}
      style={{ "--score": `${String(total)}%` } as React.CSSProperties}
    >
      <div>
        <strong>{quality ? total.toFixed(1) : "—"}</strong>
        <span>{t("outOf100")}</span>
      </div>
    </div>
  );
}
