import { useState } from "react";

import { get } from "../../api/client";
import { EmptyState, Select, Surface } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";
import { date, shortId } from "../../lib/format";

import { DeliveryCandidate } from "./DeliveryCandidate";
import "./delivery-review.css";

import type { Version } from "../../api/types";

export function DeliveryReview({
  datasetId,
  versions,
  onChanged,
}: {
  datasetId: string;
  versions: Version[];
  onChanged?: () => void;
}) {
  const { t, locale } = useI18n();
  const [selection, setSelection] = useState("");
  const [baselineId, setBaselineId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<Version | null>(null);
  const [error, setError] = useState("");
  const ordered = [
    ...versions.filter((item) => item.id !== snapshot?.id),
    ...(snapshot ? [snapshot] : []),
  ].sort((a, b) => b.created_at - a.created_at || b.id.localeCompare(a.id));
  const candidateId = selection || ordered[0]?.id || "";
  const candidate = ordered.find((item) => item.id === candidateId);
  const baselines = ordered.filter((item) => item.id !== candidateId);
  const baseline = baselineId === null ? (baselines[0]?.id ?? "") : baselineId;
  const baselineVersion = baselines.find((item) => item.id === baseline);
  const optionText = (item: Version) =>
    t("deliveryVersionLabel", {
      id: shortId(item.id),
      count: item.file_count,
      date: date(item.created_at, locale),
    });

  async function corrected(versionId: string) {
    setBaselineId(candidateId);
    setSelection(versionId);
    setError("");
    onChanged?.();
    try {
      const saved = await get<Version[]>(
        `/api/datasets/${encodeURIComponent(datasetId)}/versions`,
      );
      const created = saved.find((item) => item.id === versionId);
      if (!created) throw new Error(t("someDataIsNotAvailableYet"));
      setSnapshot(created);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  return (
    <Surface
      as="section"
      className="delivery-review"
      aria-label={t("deliveryReview")}
    >
      <header className="delivery-header">
        <h3>{t("deliveryReview")}</h3>
        <p className="muted">{t("deliveryReviewIntro")}</p>
      </header>
      {ordered.length === 0 ? (
        <EmptyState title={t("trainingNoVersions")} />
      ) : (
        <div className="version-controls">
          <label>
            {t("deliveryCandidate")}
            <Select
              value={candidateId}
              onChange={(event) => {
                setSelection(event.target.value);
                setBaselineId(null);
                setError("");
              }}
            >
              {!candidate && (
                <option value={candidateId}>{shortId(candidateId)}</option>
              )}
              {ordered.map((item) => (
                <option key={item.id} value={item.id}>
                  {optionText(item)}
                </option>
              ))}
            </Select>
          </label>
          <label>
            {t("deliveryBaseline")}
            <Select
              value={baselineVersion?.id ?? ""}
              onChange={(event) => {
                setBaselineId(event.target.value);
              }}
            >
              <option value="">{t("deliveryNoBaseline")}</option>
              {baselines.map((item) => (
                <option key={item.id} value={item.id}>
                  {optionText(item)}
                </option>
              ))}
            </Select>
          </label>
        </div>
      )}
      {!candidate && !!candidateId && !error && (
        <p role="status">{t("loadingData")}</p>
      )}
      {error && !candidate && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {candidate && (
        <DeliveryCandidate
          key={candidate.id}
          datasetId={datasetId}
          version={candidate}
          baseline={baselineVersion}
          corrected={candidate.id === snapshot?.id}
          onCorrected={(id) => void corrected(id)}
          onChanged={onChanged}
        />
      )}
    </Surface>
  );
}
