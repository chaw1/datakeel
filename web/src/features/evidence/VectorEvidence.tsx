import { useEffect, useState } from "react";

import { decideAssertion, queryVectors } from "../../api/evidence";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import { VectorMeasurement } from "./VectorMeasurement";
import { VectorReport } from "./VectorReport";
import "./vector-evidence.css";

import type {
  Assertion,
  VectorQuery,
  VectorQueryResult,
} from "../../api/types";
import type { SyntheticEvent } from "react";

export function VectorEvidence({
  datasetId,
  onAdd,
  onReviewed,
}: {
  datasetId: string;
  onAdd: (assertion: Assertion) => Promise<void>;
  onReviewed: () => void;
}) {
  const { t } = useI18n();
  const composing = useCompositionGuard();
  const [runId, setRunId] = useState("");
  const [kind, setKind] =
    useState<NonNullable<VectorQuery["kind"]>>("duplicate");
  const [reference, setReference] = useState("");
  const [cluster, setCluster] = useState("");
  const [status, setStatus] = useState<Assertion["status"]>("candidate");
  const [query, setQuery] = useState<VectorQuery | null>(null);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [result, setResult] = useState<VectorQueryResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (!query) return;
    let active = true;
    void queryVectors(query)
      .then((value) => {
        if (active) {
          setResult(value);
          setBusy(false);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : String(reason));
          setBusy(false);
        }
      });
    return () => {
      active = false;
    };
  }, [query]);
  function load(next: VectorQuery) {
    setResult(null);
    setError("");
    setNotice("");
    setBusy(true);
    setQuery(next);
  }
  function submit(event: SyntheticEvent) {
    event.preventDefault();
    if (composing()) return;
    setCursors([null]);
    load({
      run_id: runId.trim(),
      dataset_id: datasetId,
      kind,
      reference_id: reference || null,
      cluster_id: cluster || null,
      statuses: [status],
      page_size: 20,
      subject_ids: [],
    });
  }
  async function act(assertion: Assertion, decision?: Assertion["status"]) {
    if (busy || composing() || !query) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (decision) {
        const run = await decideAssertion(
          assertion.id ?? "",
          decision,
          t("evDecisionReason"),
        );
        if (run.status !== "SUCCEEDED")
          throw new Error(run.error || t("evActionFailed"));
        onReviewed();
        setCursors([null]);
        load({ ...query, cursor: null });
      } else {
        await onAdd(assertion);
        setNotice(t("vecAdded"));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="card vector-evidence">
      <summary>{t("vecTitle")}</summary>
      <p>{t("vecIntro")}</p>
      <form onSubmit={submit}>
        <label>
          {t("vecRun")}
          <input
            required
            value={runId}
            onChange={(e) => {
              setRunId(e.target.value);
            }}
          />
        </label>
        <label>
          {t("vecKind")}
          <select
            value={kind}
            onBlur={(event) => {
              setKind(event.target.value as NonNullable<VectorQuery["kind"]>);
            }}
            onChange={(e) => {
              setKind(e.target.value as NonNullable<VectorQuery["kind"]>);
            }}
          >
            {(["duplicate", "cluster", "outlier", "coverage"] as const).map(
              (value) => (
                <option key={value} value={value}>
                  {t(`vecKind_${value}`)}
                </option>
              ),
            )}
          </select>
        </label>
        <label>
          {t("vecReferenceFilter")}
          <input
            value={reference}
            onChange={(e) => {
              setReference(e.target.value);
            }}
          />
        </label>
        <label>
          {t("vecClusterFilter")}
          <input
            value={cluster}
            onChange={(e) => {
              setCluster(e.target.value);
            }}
          />
        </label>
        <label>
          {t("evState")}
          <select
            value={status}
            onBlur={(event) => {
              setStatus(event.target.value as Assertion["status"]);
            }}
            onChange={(e) => {
              setStatus(e.target.value as Assertion["status"]);
            }}
          >
            {(["candidate", "accepted", "rejected"] as const).map((value) => (
              <option key={value} value={value}>
                {t(value)}
              </option>
            ))}
          </select>
        </label>
        <button className="button" disabled={busy} type="submit">
          {t("vecQuery")}
        </button>
      </form>
      {busy && <p role="status">{t("evBusy")}</p>}
      {error && (
        <p role="alert">
          {t("vecRestart")} · {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {result && (
        <>
          <VectorReport result={result} />
          <p>{t("evResultCount", { count: result.total })}</p>
          {result.items.map((assertion) => (
            <article key={assertion.id}>
              <h3>
                <code>
                  {assertion.subject.asset_id}@{assertion.subject.version}
                </code>{" "}
                · {t(assertion.status)}
              </h3>
              <VectorMeasurement assertion={assertion} />
              {(["accepted", "rejected", "candidate"] as const).map((value) => (
                <button
                  className="button"
                  key={value}
                  disabled={
                    busy ||
                    value === assertion.status ||
                    result.status !== "current"
                  }
                  onClick={() => {
                    void act(assertion, value);
                  }}
                >
                  {t(value)}
                </button>
              ))}
              {assertion.predicate === "coverage_gap" && (
                <button
                  className="button"
                  disabled={busy || result.status !== "current"}
                  onClick={() => {
                    void act(assertion);
                  }}
                >
                  {t("vecAdd")}
                </button>
              )}
            </article>
          ))}
          <nav aria-label={t("vecPages")}>
            <button
              className="button"
              disabled={busy || cursors.length < 2}
              onClick={() => {
                if (!query) return;
                const next = cursors.slice(0, -1);
                setCursors(next);
                load({ ...query, cursor: next.at(-1) ?? null });
              }}
            >
              {t("evPrevious")}
            </button>
            <span>{t("evPage", { page: cursors.length })}</span>
            <button
              className="button"
              disabled={busy || !result.next_cursor}
              onClick={() => {
                if (!query) return;
                setCursors([...cursors, result.next_cursor]);
                load({ ...query, cursor: result.next_cursor });
              }}
            >
              {t("evNext")}
            </button>
          </nav>
        </>
      )}
    </details>
  );
}
