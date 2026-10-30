import { useState } from "react";

import { getTaskWorkbench } from "../../api/production";
import { useI18n } from "../../i18n/useI18n";

import { actionMessage, actionProblem } from "./actionErrors";
import { mutateProduction } from "./actions";
import { attributeFields, withDefaults } from "./editors/attributes";
import { defaultTemplate } from "./model";

import type { useTaskSessionData } from "./useTaskSessionData";
import type { ProjectWorkbench, TaskWorkbench } from "../../api/production";

export type TaskOperation = "submit" | "approve" | "rework";

/** Submit and review with explicit, localized outcomes and a retry for concurrent changes. */
export function useTaskActions({
  task,
  project,
  data,
  editable,
  reviewable,
  canSync,
  isIdentityVerified,
  onChanged,
}: {
  task: TaskWorkbench;
  project: ProjectWorkbench;
  data: ReturnType<typeof useTaskSessionData>;
  editable: boolean;
  reviewable: boolean;
  canSync: boolean;
  isIdentityVerified?: () => boolean;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const { session, refreshSnapshot, validate } = data;
  const [error, setError] = useState("");
  const [retry, setRetry] = useState<TaskOperation | null>(null);
  const [busy, setBusy] = useState(false);
  const [issue, setIssue] = useState("");
  /** Fill record defaults, then name the first missing or invalid attribute, if any. */
  function blockingAttribute() {
    const fields = attributeFields(
      project.template ?? defaultTemplate,
      "record",
    );
    const current = session.annotation;
    const attributes = withDefaults(current.attributes, fields);
    const next =
      JSON.stringify(attributes) === JSON.stringify(current.attributes ?? {})
        ? current
        : { ...current, attributes };
    if (next !== current) session.edit(next);
    return validate(next);
  }
  async function perform(operation: TaskOperation) {
    if (busy || (operation === "submit" ? !editable : !reviewable)) return;
    setRetry(null);
    if (!canSync || isIdentityVerified?.() === false) {
      setError(t("wbOffline"));
      return;
    }
    if (operation === "rework" && !issue.trim()) {
      setError(t("wbReviewRequired"));
      return;
    }
    const blocked = operation === "submit" ? blockingAttribute() : "";
    if (blocked) {
      setError(t("wbSubmitBlocked", { reason: blocked }));
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (!(await session.flush())) return;
      const fresh = await getTaskWorkbench(task.task.id);
      if (isIdentityVerified?.() === false) {
        setError(t("wbOffline"));
        return;
      }
      if (
        operation !== "submit" &&
        (fresh.task.latest_revision_id ?? null) !== session.revisionId
      ) {
        await session.reload();
        setError(t("wbReviewChanged"));
        return;
      }
      await mutateProduction(
        operation === "submit" ? "submit_task" : "review_task",
        {
          task_id: task.task.id,
          ...(operation === "submit"
            ? {}
            : {
                revision_id: session.revisionId ?? "",
                decision: operation,
                issues: operation === "rework" ? [issue.trim()] : [],
              }),
        },
      );
      await refreshSnapshot();
      onChanged();
    } catch (reason) {
      if (actionProblem(reason) === "changed") setRetry(operation);
      setError(actionMessage(reason, t, t("wbSaveError")));
    } finally {
      setBusy(false);
    }
  }
  return { perform, busy, error, setError, retry, issue, setIssue };
}
