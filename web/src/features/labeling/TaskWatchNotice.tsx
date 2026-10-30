import { useI18n } from "../../i18n/useI18n";

import { stateMessages } from "./model";

import type { TaskChange } from "./useTaskWatch";
import type { AnnotationRecord } from "../../api/production";

function clock(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** Save the local draft as a JSON file so nothing typed is lost after a reclaim. */
export function exportDraft(annotation: AnnotationRecord, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(annotation, null, 2)], {
      type: "application/json",
    }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `${name.replace(/\.[^.]+$/, "")}-draft.json`;
  link.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 0);
}

/** Lease countdown, renewal failures, reclaim lock and "changed elsewhere" notices. */
export function TaskWatchNotice({
  remaining,
  renewals,
  heartbeatError,
  onRenew,
  locked,
  change,
  issues = [],
  onExport,
  onReload,
  onBack,
}: {
  remaining: number | null;
  renewals: number;
  heartbeatError: string;
  onRenew: () => void;
  locked: boolean;
  change: TaskChange | null;
  /** Reviewer notes behind the current rework round. */
  issues?: string[];
  onExport: () => void;
  onReload: () => void;
  onBack: () => void;
}) {
  const { t } = useI18n();
  const back = (
    <button type="button" onClick={onBack}>
      {t("wbBackToList")}
    </button>
  );
  if (locked)
    return (
      <div className="wb-watch wb-watch-locked" role="alert">
        <strong>{t("wbTaskReclaimed")}</strong>
        <span>{t("wbTaskReclaimedDetail")}</span>
        <button type="button" className="button primary" onClick={onExport}>
          {t("wbExportDraft")}
        </button>
        {back}
      </div>
    );
  return (
    <>
      {remaining !== null && (
        <p className="wb-lease" data-remaining={remaining}>
          {t("wbLeaseRemaining", { time: clock(remaining), count: renewals })}
        </p>
      )}
      {heartbeatError && (
        <div className="wb-watch" role="alert">
          <span>{t("wbRenewFailed", { reason: heartbeatError })}</span>
          <button type="button" onClick={onRenew}>
            {t("wbRenewNow")}
          </button>
        </div>
      )}
      {change && (
        <div className="wb-watch" role="alert">
          <span>
            {change.kind === "returned"
              ? t("wbTaskReturned")
              : change.kind === "edited"
                ? t("wbTaskEditedElsewhere")
                : t("wbTaskStateChanged", {
                    state: t(stateMessages[change.state]),
                  })}
          </span>
          {change.kind === "returned" && issues.length > 0 && (
            <span className="wb-watch-issues">
              {t("wbReturnedIssues", { issues: issues.join("; ") })}
            </span>
          )}
          <button type="button" className="button primary" onClick={onReload}>
            {t("wbReload")}
          </button>
          {back}
        </div>
      )}
    </>
  );
}
