import { useI18n } from "../../i18n/useI18n";

import { resultStatuses, ruleKinds, ruleTarget } from "./ruleLabels";

import type { DqRuleView } from "../../api/qualityRules";

export function RuleList({
  views,
  selectedId,
  onSelect,
}: {
  views: DqRuleView[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="card table-scroll dq-rule-list">
      <table>
        <thead>
          <tr>
            <th>{t("dqName")}</th>
            <th>{t("dqTarget")}</th>
            <th>{t("dqKind")}</th>
            <th>{t("dqLatest")}</th>
            <th>{t("dqOwner")}</th>
          </tr>
        </thead>
        <tbody>
          {views.map((view) => (
            <tr
              key={view.rule.id}
              className={selectedId === view.rule.id ? "dq-selected" : ""}
            >
              <td>
                <button
                  className="text-button"
                  aria-pressed={selectedId === view.rule.id}
                  onClick={() => {
                    onSelect(view.rule.id);
                  }}
                >
                  {view.rule.name}
                </button>
                <span className="dq-rule-meta">
                  {t("dqRevision", { revision: view.rule.revision })} ·{" "}
                  {t(view.rule.severity === "warn" ? "dqWarn" : "dqError")}
                </span>
              </td>
              <td>{ruleTarget(view.rule)}</td>
              <td>{t(ruleKinds[view.rule.kind])}</td>
              <td>
                <span
                  className={`dq-status dq-${view.latest_result?.status ?? "pending"}`}
                >
                  {view.latest_result
                    ? t(resultStatuses[view.latest_result.status])
                    : t("dqNotRun")}
                </span>
              </td>
              <td>{view.rule.owner}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!views.length && <p className="empty-state">{t("dqEmpty")}</p>}
    </div>
  );
}
