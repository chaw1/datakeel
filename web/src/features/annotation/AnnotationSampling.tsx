import { useState } from "react";

import { createSample } from "../../api/annotation";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";

import { AnnotationInspection } from "./AnnotationInspection";

import type {
  AnnotationOverview,
  AnnotationReport,
} from "../../api/annotation";

const aqlColumns = [
  0.01, 0.015, 0.025, 0.04, 0.065, 0.1, 0.15, 0.25, 0.4, 0.65, 1, 1.5, 2.5, 4,
  6.5, 10,
];

export function AnnotationSampling({
  report,
  overview,
  onChanged,
}: {
  report: AnnotationReport;
  overview: AnnotationOverview;
  onChanged: () => void;
}) {
  const { t, locale } = useI18n();
  const [method, setMethod] = useState<"aql" | "ratio">("aql");
  const [aql, setAql] = useState("2.5");
  const [ratio, setRatio] = useState("0.1");
  const [acceptance, setAcceptance] = useState("0");
  const [seed, setSeed] = useState("42");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const plans = overview.sampling_plans.filter(
    (item) => item.batch_id === report.id,
  );
  const inspections = overview.inspections.filter(
    (item) => item.batch_id === report.id,
  );
  const active = plans.find(
    (item) =>
      !inspections.some((inspection) => inspection.sampling_id === item.id),
  );
  async function draw() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await createSample(report.dataset_id, {
        batch_id: report.id,
        method,
        seed: Number(seed),
        aql: Number(aql),
        ...(method === "ratio"
          ? { ratio: Number(ratio), acceptance_number: Number(acceptance) }
          : {}),
      });
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <h3>{t("annotationSampling")}</h3>
      <p>{t("annotationSamplingHint")}</p>
      <form
        className="annotation-form"
        onSubmit={(event) => {
          event.preventDefault();
          void draw();
        }}
      >
        <label>
          {t("annotationMethod")}
          <select
            value={method}
            onChange={(event) => {
              setMethod(event.target.value === "ratio" ? "ratio" : "aql");
            }}
            onBlur={(event) => {
              setMethod(event.target.value === "ratio" ? "ratio" : "aql");
            }}
          >
            <option value="aql">{t("annotationAqlMethod")}</option>
            <option value="ratio">{t("annotationRatioMethod")}</option>
          </select>
        </label>
        {method === "aql" ? (
          <label>
            {t("annotationAql")}
            <select
              value={aql}
              onChange={(event) => {
                setAql(event.target.value);
              }}
              onBlur={(event) => {
                setAql(event.target.value);
              }}
            >
              {aqlColumns.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <>
            <label>
              {t("annotationRatio")}
              <input
                type="number"
                min="0.0001"
                max="1"
                step="any"
                value={ratio}
                required
                onChange={(event) => {
                  setRatio(event.target.value);
                }}
              />
            </label>
            <label>
              {t("annotationAcceptanceCount")}
              <input
                type="number"
                min="0"
                step="1"
                value={acceptance}
                required
                onChange={(event) => {
                  setAcceptance(event.target.value);
                }}
              />
            </label>
          </>
        )}
        <label>
          {t("annotationSeed")}
          <input
            type="number"
            min="0"
            max="4294967295"
            value={seed}
            required
            onChange={(event) => {
              setSeed(event.target.value);
            }}
          />
        </label>
        <button className="button" disabled={busy}>
          {t(busy ? "annotationBusy" : "annotationCreateSample")}
        </button>
      </form>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {active && (
        <AnnotationInspection
          key={active.id}
          sample={active}
          onChanged={onChanged}
        />
      )}
      <h4>{t("annotationHistory")}</h4>
      {!inspections.length ? (
        <p>{t("annotationNoInspections")}</p>
      ) : (
        <ol>
          {inspections.map((inspection) => (
            <li key={inspection.id}>
              <strong>
                {t(
                  inspection.accepted
                    ? "annotationAccepted"
                    : "annotationRejected",
                )}
              </strong>{" "}
              · {inspection.defective_count} / {inspection.checks.length} ·{" "}
              {date(inspection.created_at, locale)}
              <details>
                <summary>{t("annotationReason")}</summary>
                <ul>
                  {inspection.checks
                    .filter((check) => check.defective)
                    .map((check) => (
                      <li key={check.sample_id}>
                        {check.sample_id}: {check.reason}
                      </li>
                    ))}
                </ul>
              </details>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
