import { useI18n } from "../../../i18n/useI18n";

import { AIReviewPanel } from "./AIReviewPanel";
import { HIGH_RISK, tierMessages } from "./format";

import type { ObjectRef } from "./format";
import type { TaskWorkbench } from "../../../api/production";

/**
 * What the model and the AI pre-review say about this task, beside the editor: the latest
 * model draft's tier, the way back to a draft hidden behind an empty start, and the risk.
 */
export function TaskAiNotes({
  task,
  personal,
  reviewable,
  scratch,
  revisionId,
  onUseDraft,
  onLocate,
}: {
  task: TaskWorkbench;
  personal: boolean;
  reviewable: boolean;
  /** The editor started empty over a low-confidence draft. */
  scratch: boolean;
  /** The revision the editor shows; locating only makes sense on the scored one. */
  revisionId: string | null;
  /** Load the hidden draft; absent when nothing may be edited or work has begun. */
  onUseDraft?: () => void;
  onLocate: (object: ObjectRef) => void;
}) {
  const { t } = useI18n();
  const draft = task.revisions
    .filter((revision) => revision.source === "model")
    .at(-1);
  const tier = draft?.confidence_tier;
  const review = task.ai_review;
  const own =
    personal && review?.decision === "personal" && review.risk >= HIGH_RISK;
  return (
    <>
      {tier && (
        <div className="wb-model-draft">
          <p className="muted">
            {t("wbModelTier", { tier: t(tierMessages[tier]) })}
          </p>
          {scratch && <p>{t("wbScratchStart")}</p>}
          {scratch && onUseDraft && (
            <button type="button" onClick={onUseDraft}>
              {t("wbUseModelDraft")}
            </button>
          )}
        </div>
      )}
      {review && (reviewable || own) && (
        <AIReviewPanel
          review={review}
          own={!reviewable}
          onLocate={review.revision_id === revisionId ? onLocate : undefined}
        />
      )}
    </>
  );
}
