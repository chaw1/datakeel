import { useI18n } from "../../i18n/useI18n";

import type { ActionPlan } from "../../api/types";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : "";
}

function list(value: unknown, fallback: string): string {
  return Array.isArray(value) && value.length
    ? JSON.stringify(value)
    : fallback;
}

export function ApprovalMetricDraftObject({ plan }: { plan: ActionPlan }) {
  const { t } = useI18n();
  const definition = record(plan.canonical_params.definition);
  const measure = record(definition.measure);
  const time = record(definition.time);
  const fields = [
    ["metadataConfirmationTarget", text(plan.canonical_params.draft_id)],
    [
      "metadataMetricIdentity",
      `${text(definition.name)} · ${text(definition.id)}`,
    ],
    ["metadataMetricVersion", text(definition.version)],
    ["catOwner", text(definition.owner)],
    ["metadataDescription", text(definition.description)],
    ["catTableType", text(measure.table)],
    [
      "metadataMetricMeasure",
      `${text(measure.aggregation)}(${text(measure.column)})`,
    ],
    ["metadataMetricTime", `${text(time.column)} · ${text(time.granularity)}`],
    ["metadataMetricFilters", list(definition.filters, t("metadataNoFilters"))],
    [
      "metadataMetricDimensions",
      list(definition.dimensions, t("metadataNoDimensions")),
    ],
    ["metadataMetricCaveats", list(definition.caveats, t("metadataNoCaveats"))],
  ] as const;
  return (
    <section
      className="approval-objects"
      aria-label={t("approvalObjects", { count: 1 })}
    >
      <h4>{t("approvalObjects", { count: 1 })}</h4>
      <dl className="approval-fields">
        {fields.map(([label, value]) => (
          <div key={label}>
            <dt>{t(label)}</dt>
            <dd>{value || t("catNotSet")}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
