import { useI18n } from "../../i18n/useI18n";

import type { components } from "../../api/generated";

type Summary = components["schemas"]["VersionSummary"];

export function VersionSummary({
  before,
  after,
}: {
  before: Summary;
  after: Summary;
}) {
  const { t } = useI18n();
  return (
    <dl className="version-summary">
      <div>
        <dt>{t("versionAnnotationCount")}</dt>
        <dd>
          {before.annotation_count} → {after.annotation_count}
        </dd>
      </div>
      <div>
        <dt>{t("versionLabelCount")}</dt>
        <dd>
          {before.label_count} → {after.label_count}
        </dd>
      </div>
      <div>
        <dt>{t("versionQualityScore")}</dt>
        <dd>
          {before.quality_score} → {after.quality_score}
        </dd>
      </div>
      <div>
        <dt>{t("versionEvidenceDecisions")}</dt>
        <dd>
          <code>
            {JSON.stringify(before.evidence_decisions)} →{" "}
            {JSON.stringify(after.evidence_decisions)}
          </code>
        </dd>
      </div>
    </dl>
  );
}
