import { useI18n } from "../../i18n/useI18n";
import { objectHref } from "../object/navigation";

import type { ActionPlan } from "../../api/types";

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
function text(value: unknown): string {
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : "";
}
function items(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record) : [];
}

export function ApprovalStandardObjects({ plan }: { plan: ActionPlan }) {
  const { t, locale } = useI18n();
  const mapping = record(plan.canonical_params.mapping);
  const definition = record(plan.canonical_params.definition);
  const contract = record(plan.canonical_params.contract);
  const definitions =
    plan.action_type === "import_standards"
      ? [...items(contract.standards), ...items(contract.code_lists)]
      : Object.keys(definition).length
        ? [definition]
        : [];
  const columnId = text(mapping.column_id);
  return (
    <section
      className="approval-objects"
      aria-label={t("stdAffectedObjects", { count: plan.impact.object_count })}
    >
      <h4>{t("stdAffectedObjects", { count: plan.impact.object_count })}</h4>
      {columnId && (
        <dl className="catalog-definition">
          <dt>{t("stdColumn")}</dt>
          <dd>
            <a
              href={objectHref({ kind: "column", id: columnId, tab: "facts" })}
            >
              {columnId}
            </a>
          </dd>
          <dt>{t("stdStandard")}</dt>
          <dd>
            <code>{text(mapping.standard_code)}</code>
          </dd>
        </dl>
      )}
      {plan.action_type === "rollback_standards" && (
        <p>
          {t("stdRevision", { revision: text(plan.canonical_params.revision) })}
        </p>
      )}
      {definitions.length > 0 && (
        <ol>
          {definitions.map((item) => (
            <li key={text(item.code)}>
              <strong>
                {text(item[locale === "zh" ? "name_zh" : "name_en"]) ||
                  text(item.name) ||
                  text(item.code)}
              </strong>
              <span>
                <code>{text(item.code)}</code> · {t("version")}{" "}
                {text(item.version)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
