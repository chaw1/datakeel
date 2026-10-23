import { useState } from "react";

import { localizedObjectName } from "../../i18n/graphCatalogNames";
import { useI18n } from "../../i18n/useI18n";
import { bytes } from "../../lib/format";
import { isObjectKind, objectHref } from "../object/navigation";

import { ApprovalMetricObject } from "./ApprovalMetricObject";
import { isMetricPlan } from "./metricObject";

import type { ActionPlan } from "../../api/types";

export function ApprovalObjects({ plan }: { plan: ActionPlan }) {
  const { t, locale } = useI18n();
  const [limit, setLimit] = useState(5);
  const objects = plan.manifest.objects;
  if (isMetricPlan(plan))
    return <ApprovalMetricObject key={plan.plan_digest} plan={plan} />;
  return (
    <section
      className="approval-objects"
      aria-label={t("approvalObjects", { count: objects.length })}
    >
      <h4>{t("approvalObjects", { count: objects.length })}</h4>
      {!objects.length && <p>{t("approvalNoObjects")}</p>}
      <ol>
        {objects.slice(0, limit).map((item) => {
          const ref = item.asset_ref;
          const name =
            item.properties.filename ??
            item.properties.name ??
            ref.display_name;
          const label = localizedObjectName(
            ref.asset_type,
            typeof name === "string" && name ? name : ref.asset_id,
            locale,
          );
          const quality = item.properties.quality;
          return (
            <li key={`${ref.asset_id}:${ref.version ?? ""}`}>
              {isObjectKind(ref.asset_type) ? (
                <a
                  href={objectHref({
                    kind: ref.asset_type,
                    id: ref.asset_id,
                    datasetId: plan.manifest.query.dataset_id ?? undefined,
                    versionId: ref.version ?? undefined,
                    tab: "facts",
                  })}
                >
                  {label}
                </a>
              ) : (
                <code>{label}</code>
              )}
              <span>
                {bytes(item.size)}
                {typeof quality === "number" &&
                  ` · ${t("approvalQuality", { score: quality.toFixed(1) })}`}
              </span>
            </li>
          );
        })}
      </ol>
      {objects.length > limit && (
        <button
          className="text-button"
          type="button"
          onClick={() => {
            setLimit(limit + 25);
          }}
        >
          {t("approvalMoreObjects", { count: objects.length - limit })}
        </button>
      )}
    </section>
  );
}
