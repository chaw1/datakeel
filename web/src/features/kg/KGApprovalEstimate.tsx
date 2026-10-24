import { useI18n } from "../../i18n/useI18n";

import type { ActionPlan } from "../../api/types";

export function KGApprovalEstimate({ plan }: { plan: ActionPlan }) {
  const { t } = useI18n();
  const estimate = plan.impact.kg_estimate;
  if (!estimate) return null;
  return (
    <section className="kg-approval-estimate" aria-label={t("kgPrepare")}>
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
          <dt>{t("kgDocuments")}</dt>
          <dd>{estimate.documents}</dd>
        </div>
        <div>
          <dt>{t("kgBlocks")}</dt>
          <dd>{estimate.blocks}</dd>
        </div>
        <div>
          <dt>{t("kgInputEstimate")}</dt>
          <dd>{estimate.input_tokens}</dd>
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
