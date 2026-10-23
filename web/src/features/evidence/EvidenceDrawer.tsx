import { useEffect, useRef, useState } from "react";

import { decideAssertion, evidencePath } from "../../api/evidence";
import { lineageHref } from "../../app/lineageNavigation";
import { Footnotes } from "../../components/Footnotes";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { useResource } from "../../lib/useResource";

import { AssertionReview } from "./AssertionReview";
import { assertionConcept } from "./assertions";
import { CaptionEvidence } from "./CaptionEvidence";
import { anchors, concepts, evidenceSources, reviewOrder } from "./matrix";
import { SamplePreview } from "./SamplePreview";

import type { Assertion, EvidenceSample } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";
import type { KeyboardEvent } from "react";

export function EvidenceDrawer({
  sample,
  onClose,
  onReviewed,
  onOpenGraph,
}: {
  sample: EvidenceSample;
  onClose: () => void;
  onReviewed: () => void;
  onOpenGraph: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  const resource = useResource<EvidenceSample>(
    evidencePath(sample.asset_ref.asset_id, sample.source_version),
  );
  const [activeId, setActiveId] = useState("");
  const [hovered, setHovered] = useState("");
  const isComposing = useCompositionGuard();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement;
    if (element?.showModal) element.showModal();
    else element?.setAttribute("open", "");
    return () => {
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);
  const value = resource.value;
  const ordered = reviewOrder(value?.assertions ?? []);
  const current = ordered.find((item) => item.id === activeId) ?? ordered.at(0);
  const currentId = current?.id ?? "";
  const activeConcept =
    hovered || (current ? assertionConcept(current) : "") || "";
  const target: LineageTarget = {
    datasetId: sample.dataset_id,
    assetId: sample.asset_ref.asset_id,
    includeSemantic: true,
  };
  async function decide(assertion: Assertion, status: Assertion["status"]) {
    if (
      !assertion.id ||
      busy ||
      resource.loading ||
      isComposing() ||
      assertion.status === status
    )
      return;
    setActiveId(assertion.id);
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const run = await decideAssertion(
        assertion.id,
        status,
        t("evDecisionReason"),
      );
      if (run.status !== "SUCCEEDED")
        throw new Error(run.error || t("evActionFailed"));
      setSaved(true);
      resource.reload();
      onReviewed();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  function keyboard(event: KeyboardEvent<HTMLDialogElement>) {
    if (isComposing(event.nativeEvent)) {
      if (
        event.key === "Enter" ||
        event.key === "Escape" ||
        (event.key === " " &&
          event.target instanceof HTMLElement &&
          Boolean(event.target.closest("button")))
      )
        event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (
      event.altKey ||
      event.metaKey ||
      event.ctrlKey ||
      event.repeat ||
      !current ||
      (event.target instanceof HTMLElement &&
        event.target.matches("input, textarea, select, [contenteditable=true]"))
    )
      return;
    if (event.key === "j" || event.key === "k") {
      event.preventDefault();
      const next = ordered.at(
        Math.max(
          0,
          Math.min(
            ordered.length - 1,
            ordered.indexOf(current) + (event.key === "j" ? 1 : -1),
          ),
        ),
      );
      if (next?.id) {
        setActiveId(next.id);
        setHovered("");
        Array.from(
          dialog.current?.querySelectorAll<HTMLElement>(
            "[data-assertion-id]",
          ) ?? [],
        )
          .find((element) => element.dataset.assertionId === next.id)
          ?.scrollIntoView({ block: "nearest" });
      }
    } else if (event.key === "a" || event.key === "r") {
      event.preventDefault();
      void decide(current, event.key === "a" ? "accepted" : "rejected");
    }
  }
  return (
    <dialog
      className="evidence-drawer"
      ref={dialog}
      aria-label={t("evDetails")}
      onKeyDownCapture={keyboard}
      onCancel={(event) => {
        event.preventDefault();
        if (!isComposing()) onClose();
      }}
    >
      <div className="evidence-drawer-heading">
        <div>
          <span className="eyebrow">{t("evDetails")}</span>
          <h2>{sample.filename}</h2>
        </div>
        <button className="button" onClick={onClose} aria-label={t("evClose")}>
          ×
        </button>
      </div>
      <p className="evidence-keyboard">{t("evKeyboard")}</p>
      <ResourceState {...resource} onRetry={resource.reload} />
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {saved && (
        <p className="evidence-success" role="status">
          {t("evReviewSaved")}
        </p>
      )}
      {value && (
        <>
          <div className="evidence-detail-visual">
            <SamplePreview
              sample={value}
              activeId={activeConcept}
              numbers={concepts(value)}
            />
            <div>
              <span className="eyebrow">{t("evCaption")}</span>
              <CaptionEvidence
                caption={value.caption}
                spans={value.caption_spans}
                ranges={anchors(value)}
                activeId={activeConcept}
                onActive={setHovered}
              />
              <p className="small">
                {t("evQuality")}: {value.quality_score.toFixed(1)}
              </p>
              <span className="eyebrow">{t("evVersion")}</span>
              <code className="evidence-version">{value.source_version}</code>
            </div>
          </div>
          <a
            className="button"
            href={lineageHref(target)}
            onClick={(event) => {
              if (
                event.metaKey ||
                event.ctrlKey ||
                event.shiftKey ||
                event.altKey
              )
                return;
              event.preventDefault();
              onOpenGraph(target);
            }}
          >
            {t("evViewGraph")}
          </a>
          {value.near_duplicates.length > 0 && (
            <section className="evidence-detail-neighbors">
              <h3>{t("evNeighbors")}</h3>
              {value.near_duplicates.map((candidate) => (
                <p key={candidate.assertion_id}>
                  <code>{candidate.asset_ref.asset_id}</code>
                  <br />
                  {t("evDirectDistance", {
                    distance: candidate.distance,
                  })}{" "}
                  · {candidate.reason}
                </p>
              ))}
            </section>
          )}
          <AssertionReview
            assertions={ordered}
            activeId={currentId}
            activeConcept={activeConcept}
            onHover={setHovered}
            numbers={concepts(value)}
            busy={busy || resource.loading}
            onLocate={setActiveId}
            onDecide={(assertion, status) => {
              void decide(assertion, status);
            }}
          />
          <Footnotes items={evidenceSources([value])} />
        </>
      )}
    </dialog>
  );
}
