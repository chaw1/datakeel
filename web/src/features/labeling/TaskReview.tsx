import { useI18n } from "../../i18n/useI18n";

export function TaskReview({
  issue,
  busy,
  onIssue,
  onReview,
}: {
  issue: string;
  busy: boolean;
  onIssue: (value: string) => void;
  onReview: (decision: "approve" | "rework") => void;
}) {
  const { t } = useI18n();
  return (
    <div className="card wb-review-controls">
      <label>
        {t("wbReviewIssue")}
        <textarea
          value={issue}
          onChange={(event) => {
            onIssue(event.target.value);
          }}
        />
      </label>
      <button
        type="button"
        className="button primary"
        disabled={busy}
        onClick={() => {
          onReview("approve");
        }}
      >
        {t("wbApprove")}
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          onReview("rework");
        }}
      >
        {t("wbRework")}
      </button>
    </div>
  );
}
