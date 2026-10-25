import { useI18n } from "../../i18n/useI18n";

import type { ActionPlan } from "../../api/types";

export function KGTranscriptionEstimate({ plan }: { plan: ActionPlan }) {
  const { t } = useI18n();
  const estimate = plan.impact.transcription_estimate;
  if (!estimate) return null;
  return (
    <section aria-label={t("kgTranscriptionEstimate")}>
      <h4>{t("kgTranscriptionEstimate")}</h4>
      <dl className="approval-fields">
        <div>
          <dt>{t("kgTargetHost")}</dt>
          <dd>{estimate.target_host ?? t("kgOffline")}</dd>
        </div>
        <div>
          <dt>{t("kgModel")}</dt>
          <dd>{estimate.model}</dd>
        </div>
        <div>
          <dt>{t("kgImageCount")}</dt>
          <dd>{estimate.images}</dd>
        </div>
        <div>
          <dt>{t("kgImageTokens")}</dt>
          <dd>{estimate.image_tokens}</dd>
        </div>
        <div>
          <dt>{t("kgOutputLimit")}</dt>
          <dd>{estimate.max_output_tokens}</dd>
        </div>
        <div>
          <dt>{t("kgCostUpper")}</dt>
          <dd>
            {estimate.cost_upper_usd == null
              ? t("kgUnknown")
              : `$${Number(estimate.cost_upper_usd).toFixed(6)}`}
          </dd>
        </div>
      </dl>
    </section>
  );
}
