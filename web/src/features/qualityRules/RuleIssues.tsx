import { useState } from "react";

import { prepareQualityIssue } from "../../api/qualityRules";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";

import { issueStatuses } from "./ruleLabels";

import type { DqIssue } from "../../api/qualityRules";
import type { ActionPlan } from "../../api/types";

export function RuleIssues({
  issues,
  onPrepared,
}: {
  issues: DqIssue[];
  onPrepared: (plan: ActionPlan) => void;
}) {
  const { t, locale } = useI18n();
  const [assignees, setAssignees] = useState<Partial<Record<string, string>>>(
    {},
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function prepare(issue: DqIssue, status: "claimed" | "resolved") {
    const assignee = assignees[issue.id] ?? issue.assignee ?? "local";
    if (busy || (status === "claimed" && !assignee.trim())) return;
    setBusy(true);
    setError("");
    try {
      onPrepared(
        await prepareQualityIssue(
          issue,
          status,
          status === "claimed" ? assignee.trim() : (issue.assignee ?? null),
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("dqActionFailed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label={t("dqIssues")} className="dq-issues">
      <h2>{t("dqIssues")}</h2>
      {!issues.length ? (
        <p className="muted">{t("dqNoIssues")}</p>
      ) : (
        <>
          <ul className="dq-issue-list">
            {issues.map((issue) => (
              <li key={issue.id}>
                <div>
                  <strong className={`dq-status dq-${issue.status}`}>
                    {t(issueStatuses[issue.status])}
                  </strong>
                  <code>{issue.rule_id}</code>
                  <span>{t("dqOccurrences", { count: issue.failures })}</span>
                  <span>{issue.assignee ?? "—"}</span>
                </div>
                {issue.status !== "resolved" && (
                  <label className="dq-assignee">
                    {t("dqAssignee")}
                    <input
                      aria-label={t("dqAssigneeFor", { rule: issue.rule_id })}
                      value={assignees[issue.id] ?? issue.assignee ?? "local"}
                      maxLength={200}
                      onChange={(event) => {
                        setAssignees({
                          ...assignees,
                          [issue.id]: event.target.value,
                        });
                      }}
                    />
                  </label>
                )}
                <dl>
                  <div>
                    <dt>{t("dqFirstSeen")}</dt>
                    <dd>{date(issue.created_at, locale)}</dd>
                  </div>
                  <div>
                    <dt>{t("dqLastSeen")}</dt>
                    <dd>{date(issue.updated_at, locale)}</dd>
                  </div>
                </dl>
                <div className="dq-controls">
                  {issue.status !== "resolved" && (
                    <button
                      className="button subtle"
                      disabled={
                        busy ||
                        !(
                          assignees[issue.id] ??
                          issue.assignee ??
                          "local"
                        ).trim()
                      }
                      onClick={() => {
                        void prepare(issue, "claimed");
                      }}
                    >
                      {t("dqClaim")}
                    </button>
                  )}
                  {issue.can_resolve && (
                    <button
                      className="button subtle"
                      disabled={busy}
                      onClick={() => {
                        void prepare(issue, "resolved");
                      }}
                    >
                      {t("dqResolve")}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
