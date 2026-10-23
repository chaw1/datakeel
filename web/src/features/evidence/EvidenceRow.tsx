import { useState } from "react";

import { TriState } from "../../components/TriState";
import { useI18n } from "../../i18n/useI18n";

import { AssertionMatrix } from "./AssertionMatrix";
import { assertionValue } from "./assertions";
import { CaptionEvidence } from "./CaptionEvidence";
import { anchors, concepts } from "./matrix";
import { SamplePreview } from "./SamplePreview";

import type { EvidenceSample } from "../../api/types";
import type { FootnoteItem } from "../../components/Footnotes";

export function EvidenceRow({
  sample,
  selected,
  onSelect,
  onInspect,
  sources,
  commonVersion,
}: {
  sample: EvidenceSample;
  selected: boolean;
  onSelect: () => void;
  onInspect: () => void;
  sources: FootnoteItem[];
  commonVersion: boolean;
}) {
  const { t } = useI18n();
  const [active, setActive] = useState("");
  const filenameParts = sample.filename.split("/");
  const parentName = filenameParts.at(-2);
  const corrupt = sample.assertions.find(
    (item) => item.predicate === "corrupt",
  );
  const candidateCount = sample.assertions.filter(
    (item) => item.status === "candidate",
  ).length;
  return (
    <tr
      className={`evidence-sample-row${selected ? " selected" : ""}`}
      data-sample-id={sample.asset_ref.asset_id}
    >
      <td>
        <input
          type="checkbox"
          aria-label={t("evSelect", { filename: sample.filename })}
          checked={selected}
          onChange={onSelect}
        />
        <span className="evidence-split">{sample.split || t("evUnknown")}</span>
      </td>
      <td>
        <button
          className="sample-inspect"
          aria-label={t("evInspect", { filename: sample.filename })}
          onClick={onInspect}
        >
          <SamplePreview
            sample={sample}
            activeId={active}
            numbers={concepts(sample)}
          />
          <strong title={sample.filename}>
            <span className="sample-path-prefix">
              {parentName ? `${parentName}/` : ""}
            </span>
            <span>{filenameParts.at(-1)}</span>
          </strong>
        </button>
        {sample.quarantined && (
          <span className="badge amber">{t("quarantined")}</span>
        )}
      </td>
      <td>
        <CaptionEvidence
          caption={sample.caption}
          spans={sample.caption_spans}
          ranges={anchors(sample)}
          activeId={active}
          onActive={setActive}
        />
        <div className="evidence-inline-notes">
          <span>
            {t("evNeighbors")}:{" "}
            {sample.near_duplicates.length ? (
              <code title={sample.near_duplicates[0].reason}>
                {sample.near_duplicates[0].asset_ref.asset_id.slice(0, 8)} ·{" "}
                {t("evDistanceShort", {
                  distance: sample.near_duplicates[0].distance,
                })}
              </code>
            ) : (
              t("evNoNeighbors")
            )}
          </span>
          {corrupt && (
            <span>
              {t("evCorrupt")}: <TriState value={assertionValue(corrupt)} />
            </span>
          )}
        </div>
      </td>
      <td>
        <AssertionMatrix
          sample={sample}
          activeId={active}
          onActive={setActive}
          sources={sources}
          onInspect={onInspect}
        />
      </td>
      <td>
        <strong className="evidence-score">
          {sample.quality_score.toFixed(1)}
        </strong>
        <button className="text-button evidence-candidates" onClick={onInspect}>
          {t("evCandidates", { count: candidateCount })}
        </button>
        {!commonVersion && (
          <code className="evidence-version">{sample.source_version}</code>
        )}
      </td>
    </tr>
  );
}
