import { useState } from "react";

import { exportTraining } from "../../api/training";
import { lineageHref } from "../../app/lineageNavigation";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { ApprovalSheet } from "../approvals/ApprovalSheet";

import type { SplitSet } from "../../api/training";
import type { ActionPlan } from "../../api/types";
import type { MessageKey } from "../../i18n/en";
import type { SubmitEvent } from "react";

const formats: Record<string, MessageKey> = {
  coco: "trainingCoco",
  yolo: "trainingYolo",
  imagefolder: "trainingImagefolder",
  text_jsonl: "trainingJsonl",
};

export function TrainingExport({ split }: { split: SplitSet }) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const [format, setFormat] = useState("coco");
  const [destination, setDestination] = useState("");
  const [annotatorId, setAnnotatorId] = useState("");
  const annotators = [
    ...new Set(
      split.members.flatMap((member) =>
        member.annotations.map((annotation) => annotation.annotator_id),
      ),
    ),
  ].sort();
  const needsAnnotator = split.members.some(
    (member) => member.annotations.length > 1,
  );
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [downloadPlan, setDownloadPlan] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function prepare(event: SubmitEvent) {
    event.preventDefault();
    if (busy || isComposing()) return;
    setBusy(true);
    setError("");
    setPlan(null);
    setDownloadPlan("");
    try {
      setPlan(
        await exportTraining(split, format, destination.trim(), annotatorId),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="training-export" aria-label={t("trainingExport")}>
      <h4>{t("trainingExport")}</h4>
      <p className="muted">{t("trainingExportHint")}</p>
      {needsAnnotator && <p className="muted">{t("trainingAnnotatorHint")}</p>}
      <form
        className="training-controls"
        onSubmit={(event) => void prepare(event)}
      >
        <label>
          {t("trainingFormat")}
          <select
            value={format}
            onBlur={(event) => {
              setFormat(event.target.value);
            }}
            onChange={(event) => {
              setFormat(event.target.value);
              setPlan(null);
              setDownloadPlan("");
            }}
          >
            {Object.entries(formats).map(([value, key]) => (
              <option key={value} value={value}>
                {t(key)}
              </option>
            ))}
          </select>
        </label>
        {!!annotators.length && (
          <label>
            {t("trainingAnnotator")}
            <select
              value={annotatorId}
              required={needsAnnotator}
              onBlur={(event) => {
                setAnnotatorId(event.target.value);
              }}
              onChange={(event) => {
                setAnnotatorId(event.target.value);
                setPlan(null);
                setDownloadPlan("");
              }}
            >
              <option value="">{t("trainingOnlyAnnotation")}</option>
              {annotators.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          {t("trainingDestination")}
          <input
            value={destination}
            required
            pattern="[^/\\\\]+[.]tar[.]gz"
            placeholder={t("trainingArchiveExample")}
            onChange={(event) => {
              setDestination(event.target.value);
              setPlan(null);
              setDownloadPlan("");
            }}
          />
        </label>
        <button
          className="button"
          type="submit"
          disabled={busy || (needsAnnotator && !annotatorId)}
        >
          {t("trainingExportReview")}
        </button>
      </form>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {plan && (
        <ApprovalSheet
          key={plan.id}
          plan={plan}
          onOpenReceipt={(target) => {
            window.location.hash = lineageHref(target);
          }}
          onResolved={(run) => {
            if (run?.status === "SUCCEEDED") setDownloadPlan(plan.id);
          }}
          onInvalidated={() => {
            setPlan(null);
          }}
        />
      )}
      {downloadPlan && (
        <p role="status">
          {t("trainingExportReady")}{" "}
          <a
            href={`/api/actions/${encodeURIComponent(downloadPlan)}/export`}
            download
          >
            {t("trainingDownload")}
          </a>
        </p>
      )}
    </section>
  );
}
