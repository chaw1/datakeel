import { useI18n } from "../../i18n/useI18n";

import { qualityObject } from "./qualityObject";

import type { ActionPlan } from "../../api/types";

export function ApprovalQualityObject({ plan }: { plan: ActionPlan }) {
  const { t } = useI18n();
  const target = qualityObject(plan);
  return (
    <section
      className="approval-objects"
      aria-label={t("approvalObjects", { count: 1 })}
    >
      <h4>{t("approvalObjects", { count: 1 })}</h4>
      <ol>
        <li>
          <strong>
            {target.name ??
              t(
                target.issue ? "dqApprovalIssueObject" : "dqApprovalRuleObject",
              )}
          </strong>
          <dl className="detail-grid">
            <div>
              <dt>{t("dqId")}</dt>
              <dd>
                <code>{target.id ?? "—"}</code>
              </dd>
            </div>
            {target.target && (
              <div>
                <dt>{t("dqTarget")}</dt>
                <dd>{target.target}</dd>
              </div>
            )}
            {(target.revision !== null || target.expectedRevision !== null) && (
              <div>
                <dt>{t("version")}</dt>
                <dd>
                  {target.revision !== null && target.expectedRevision !== null
                    ? t("dqApprovalRevisionChange", {
                        from: target.expectedRevision,
                        to: target.revision,
                      })
                    : target.revision !== null
                      ? t("dqRevision", { revision: target.revision })
                      : t("dqApprovalReviewedRevision", {
                          revision: target.expectedRevision ?? "—",
                        })}
                </dd>
              </div>
            )}
            {target.issue && (
              <>
                <div>
                  <dt>{t("dqStatus")}</dt>
                  <dd>
                    {target.status
                      ? t(
                          target.status === "claimed"
                            ? "dqClaimed"
                            : "dqResolved",
                        )
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>{t("dqAssignee")}</dt>
                  <dd>{target.assignee ?? t("dqApprovalNoAssignee")}</dd>
                </div>
              </>
            )}
          </dl>
        </li>
      </ol>
    </section>
  );
}
