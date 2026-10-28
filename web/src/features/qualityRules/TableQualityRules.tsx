import { qualityRulesPath } from "../../api/qualityRules";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import { resultStatuses } from "./ruleLabels";

import type { CatalogObject } from "../../api/catalog";
import type { DqRuleView } from "../../api/qualityRules";

import "./qualityRules.css";

export function TableQualityRules({ table }: { table: CatalogObject }) {
  const { t } = useI18n();
  const filters = {
    source_id: table.source_id ?? undefined,
    table: table.name,
    schema_name: table.schema_name ?? undefined,
  };
  const resource = useResource<DqRuleView[]>(
    table.source_id ? qualityRulesPath(filters) : null,
  );
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters))
    if (value) query.set(key, value);
  if (!table.source_id) return null;
  return (
    <section className="dq-table-rules" aria-label={t("dqTableRules")}>
      <h2>{t("dqTableRules")}</h2>
      <ResourceState {...resource} onRetry={resource.reload} />
      {resource.value &&
        (resource.value.length ? (
          <ul>
            {resource.value.map((view) => (
              <li key={view.rule.id}>
                <a
                  href={`#/quality-rules?${query.toString()}&rule=${encodeURIComponent(view.rule.id)}`}
                >
                  {view.rule.name}
                </a>
                <span
                  className={`dq-status dq-${view.latest_result?.status ?? "pending"}`}
                >
                  {view.latest_result
                    ? t(resultStatuses[view.latest_result.status])
                    : t("dqNotRun")}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t("dqEmpty")}</p>
        ))}
      <a href={`#/quality-rules?${query.toString()}`}>{t("dqOpenRules")}</a>
    </section>
  );
}
