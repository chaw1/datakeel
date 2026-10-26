import { metricPath } from "../../api/catalog";
import { localizedCatalogName } from "../../i18n/graphCatalogNames";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";
import { objectHref } from "../object/navigation";

import { metricAtPreparation, metricObject } from "./metricObject";

import type { MetricHistory } from "../../api/objects";
import type { ActionPlan } from "../../api/types";

export function ApprovalMetricObject({ plan }: { plan: ActionPlan }) {
  const { t, locale } = useI18n();
  const target = metricObject(plan);
  const history = useResource<MetricHistory>(
    plan.action_type === "rollback_metric" && target.id
      ? `${metricPath(target.id)}/history`
      : null,
  );
  const definition = history.value
    ? metricAtPreparation(plan, history.value)
    : null;
  const version = definition?.version ?? target.version;
  const label = definition?.name ?? target.name;
  const englishName = definition?.english_name ?? target.englishName;
  return (
    <section
      className="approval-objects"
      aria-label={t("approvalObjects", { count: 1 })}
    >
      <h4>{t("approvalObjects", { count: 1 })}</h4>
      <ol>
        <li>
          <a href={objectHref({ kind: "metric", id: target.id, tab: "facts" })}>
            {locale === "en" && englishName
              ? englishName
              : localizedCatalogName(label, t)}
          </a>
          <span>
            {version !== null
              ? t("approvalMetricVersions", { from: version, to: version + 1 })
              : t(
                  history.loading
                    ? "approvalMetricLoading"
                    : "approvalMetricUnavailable",
                )}
          </span>
        </li>
      </ol>
      {history.error && (
        <button className="text-button" type="button" onClick={history.reload}>
          {t("retry")}
        </button>
      )}
    </section>
  );
}
