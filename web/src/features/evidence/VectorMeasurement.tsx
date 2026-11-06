import { useI18n } from "../../i18n/useI18n";

import type { Assertion } from "../../api/types";

export function VectorMeasurement({ assertion }: { assertion: Assertion }) {
  const { t } = useI18n();
  const value = assertion.measurement;
  if (!value) return null;
  return (
    <dl>
      {"similarity" in value && (
        <>
          <dt>{t("vecSimilarity")}</dt>
          <dd>{value.similarity}</dd>
          <dt>{t("vecThreshold")}</dt>
          <dd>{value.threshold}</dd>
        </>
      )}
      {"eps" in value && (
        <>
          <dt>{t("vecConfig")}</dt>
          <dd>
            {t("vecConfigValue", { eps: value.eps, min: value.min_samples })}
          </dd>
        </>
      )}
      {value.type === "cluster_config" && (
        <>
          <dt>{t("vecCluster")}</dt>
          <dd>
            <code>
              {"asset_id" in assertion.object ? assertion.object.asset_id : ""}
            </code>{" "}
            · {value.role}
          </dd>
          <dt>{t("vecMembers")}</dt>
          <dd>
            {value.members.map((ref) => (
              <p key={`${ref.asset_id}:${ref.version ?? ""}`}>
                <code>
                  {ref.asset_id}@{ref.version}
                </code>
              </p>
            ))}
          </dd>
        </>
      )}
      {value.type === "outlier_config" && (
        <>
          <dt>{t("vecOutlier")}</dt>
          <dd>{t("vecNoise")}</dd>
        </>
      )}
      {value.type === "coverage" && (
        <>
          <dt>{t("vecNearest")}</dt>
          <dd>
            <code>
              {value.nearest.asset_id}@{value.nearest.version}
            </code>
          </dd>
          <dt>{t("vecReferences")}</dt>
          <dd>
            <code>{value.reference_digest}</code>
            {value.references.map((member) => (
              <p
                key={`${member.subject.asset_id}:${member.subject.version ?? ""}`}
              >
                <code>
                  {member.subject.asset_id}@{member.subject.version}
                </code>{" "}
                · {member.content_revision}
              </p>
            ))}
          </dd>
        </>
      )}
      <dt>{t("evAnchor")}</dt>
      <dd>
        {assertion.anchors.map((anchor) => (
          <p key={`${anchor.asset_ref.asset_id}:${anchor.content_revision}`}>
            <code>
              {anchor.asset_ref.asset_id}@{anchor.asset_ref.version}
            </code>{" "}
            · {anchor.content_revision}
          </p>
        ))}
      </dd>
      <dt>{t("evProducer")}</dt>
      <dd>
        <code>{assertion.producer_event_id}</code> · {assertion.extractor.id}@
        {assertion.extractor.version}
      </dd>
    </dl>
  );
}
