import { useI18n } from "../../i18n/useI18n";

import type { ActionPlan } from "../../api/types";

/** The server's TemplateUpgradePlan, shown on the plan's frozen project object. */
export interface TemplateUpgradePlan {
  project_id: string;
  template_id: string | null;
  from_template_version: number | null;
  to_template_version: number | null;
  label_set_id: string;
  from_label_set_version: number;
  to_label_set_version: number;
  labels: {
    added: string[];
    removed: string[];
    renamed: { id: string; before: string; after: string }[];
    changed: string[];
  };
  attributes: {
    added: string[];
    removed: string[];
    changed: string[];
    required: string[];
  };
  settings_changed: string[];
  task_count: number;
  annotated_task_count: number;
  annotation_object_count: number;
  invalid_task_count: number;
  invalid_object_count: number;
  invalid_tasks: {
    task_id: string;
    revision_id: string;
    sample_id: string;
    state: string;
    invalid_objects: number;
    problems: string[];
  }[];
}

export function upgradeDetails(plan: ActionPlan): TemplateUpgradePlan | null {
  const project = plan.manifest.objects.find(
    (item) => item.asset_ref.asset_type === "project",
  );
  const value = project?.properties.template_upgrade;
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as unknown as TemplateUpgradePlan)
    : null;
}

/** Plain words first: versions, what changed, and which current annotations stop passing. */
export function TemplateUpgradeSummary({
  plan,
  name = (taskId) => taskId,
}: {
  plan: ActionPlan;
  name?: (taskId: string) => string;
}) {
  const { t } = useI18n();
  const details = upgradeDetails(plan);
  if (!details) return null;
  const none = t("wbTemplateUpgradeNone");
  const list = (values: readonly string[]) =>
    values.length ? values.join(", ") : none;
  const { labels, attributes } = details;
  return (
    <div className="wb-template-upgrade">
      <p>
        {t("wbTemplateUpgradeFrom", {
          from: details.from_template_version ?? "-",
          to: details.to_template_version ?? "-",
          labelsFrom: details.from_label_set_version,
          labelsTo: details.to_label_set_version,
        })}
      </p>
      <p>
        {t("wbTemplateUpgradeLabels", {
          added: list(labels.added),
          removed: list(labels.removed),
          renamed: list(
            labels.renamed.map(
              (item) => `${item.id}: ${item.before} → ${item.after}`,
            ),
          ),
          changed: list(labels.changed),
        })}
      </p>
      <p>
        {t("wbTemplateUpgradeAttributes", {
          added: list(attributes.added),
          removed: list(attributes.removed),
          changed: list(attributes.changed),
          required: list(attributes.required),
        })}
      </p>
      {details.settings_changed.length > 0 && (
        <p>
          {t("wbTemplateUpgradeSettings", {
            settings: list(details.settings_changed),
          })}
        </p>
      )}
      <p>
        {t("wbTemplateUpgradeCounts", {
          tasks: details.task_count,
          annotated: details.annotated_task_count,
          objects: details.annotation_object_count,
        })}
      </p>
      {details.invalid_task_count ? (
        <>
          <p>
            {t("wbTemplateUpgradeInvalid", {
              tasks: details.invalid_task_count,
              objects: details.invalid_object_count,
            })}
          </p>
          <ul className="wb-template-upgrade-invalid">
            {details.invalid_tasks.map((item) => (
              <li key={item.task_id}>
                <span title={item.task_id}>{name(item.task_id)}</span>:{" "}
                {item.problems.join("; ")}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p>{t("wbTemplateUpgradeAllValid")}</p>
      )}
      <p className="muted">{t("wbTemplateUpgradeOnly")}</p>
    </div>
  );
}
