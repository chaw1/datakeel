import { useState } from "react";

import {
  analyzeTraining,
  prepareTrainingClean,
  trainingPath,
} from "../../api/trainingData";
import { lineageHref } from "../../app/lineageNavigation";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { useResource } from "../../lib/useResource";
import { PlanCard } from "../actions/PlanCard";

import { TrainingControls } from "./TrainingControls";
import { TrainingEvaluations } from "./TrainingEvaluations";
import { TrainingReportView } from "./TrainingReportView";
import "./training-data.css";

import type {
  TrainingConfig,
  TrainingEvaluation,
  TrainingRun,
} from "../../api/trainingData";
import type { ActionPlan, FileItem, Version } from "../../api/types";

export function TrainingGovernance({
  datasetId,
  versions,
  files,
  onChanged,
  initialOpen = false,
  initialVersionId,
}: {
  datasetId: string;
  versions: Version[];
  files: FileItem[];
  onChanged: () => void;
  initialOpen?: boolean;
  initialVersionId?: string;
}) {
  const { t, locale } = useI18n();
  const isComposing = useCompositionGuard();
  const [open, setOpen] = useState(initialOpen);
  const [versionId, setVersionId] = useState(
    initialVersionId ?? versions.at(0)?.id ?? "",
  );
  const [format, setFormat] = useState<TrainingConfig["format"]>("auto");
  const [maxTokens, setMaxTokens] = useState(8192);
  const [ngram, setNgram] = useState(13);
  const [evaluationIds, setEvaluationIds] = useState<string[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [latest, setLatest] = useState<TrainingRun | null>(null);
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [completed, setCompleted] = useState(false);
  const path = trainingPath(datasetId);
  const history = useResource<TrainingRun[]>(
    open && versionId
      ? `${path}?${new URLSearchParams({ version_id: versionId }).toString()}`
      : null,
  );
  const evaluations = useResource<TrainingEvaluation[]>(
    open ? `${path}/evaluations` : null,
  );
  const runs =
    latest?.version_id === versionId
      ? [latest, ...(history.value ?? []).filter((run) => run.id !== latest.id)]
      : (history.value ?? []);
  const run = runs.find((item) => item.id === selectedRunId) ?? runs.at(0);
  function invalidate() {
    setPlan(null);
    setCompleted(false);
    setError("");
  }
  function changeVersion(value: string) {
    if (value === versionId) return;
    setVersionId(value);
    setSelectedRunId("");
    setLatest(null);
    invalidate();
  }
  async function analyze() {
    if (busy || !versionId || isComposing()) return;
    setBusy(true);
    invalidate();
    try {
      const result = await analyzeTraining(datasetId, {
        version_id: versionId,
        evaluation_ids: evaluationIds,
        config: { format, max_tokens: maxTokens, contamination_ngram: ngram },
      });
      setLatest(result);
      setSelectedRunId(result.id);
      history.reload();
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("trainingFailure"));
    } finally {
      setBusy(false);
    }
  }
  async function clean() {
    if (!run || busy || isComposing()) return;
    setBusy(true);
    invalidate();
    try {
      setPlan(await prepareTrainingClean(run.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("trainingFailure"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details
      className="card training-governance"
      open={open}
      onToggle={(event) => {
        setOpen(event.currentTarget.open);
      }}
    >
      <summary>{t("trainingTitle")}</summary>
      <p>{t("trainingDescription")}</p>
      <p className="muted">{t("trainingOffline")}</p>
      {!versions.length ? (
        <p>{t("trainingNoVersions")}</p>
      ) : (
        open && (
          <>
            <TrainingControls
              versions={versions}
              versionId={versionId}
              format={format}
              maxTokens={maxTokens}
              ngram={ngram}
              busy={busy}
              onVersion={changeVersion}
              onFormat={(value) => {
                setFormat(value);
                invalidate();
              }}
              onMaxTokens={(value) => {
                setMaxTokens(value);
                invalidate();
              }}
              onNgram={(value) => {
                setNgram(value);
                invalidate();
              }}
              onAnalyze={() => {
                void analyze();
              }}
            />
            <TrainingEvaluations
              key={versionId}
              datasetId={datasetId}
              versionId={versionId}
              files={
                versions.find((item) => item.id === versionId)?.manifest ??
                files
              }
              evaluations={evaluations.value ?? []}
              selected={evaluationIds}
              onSelected={(ids) => {
                setEvaluationIds(ids);
                invalidate();
              }}
              onRegistered={evaluations.reload}
            />
            <ResourceState
              loading={history.loading || evaluations.loading}
              error={error || history.error || evaluations.error}
              onRetry={() => {
                history.reload();
                evaluations.reload();
                setError("");
              }}
            />
            {!!runs.length && (
              <label className="training-history">
                {t("trainingHistory")}
                <select
                  value={run?.id ?? ""}
                  onBlur={(event) => {
                    setSelectedRunId(event.target.value);
                  }}
                  onChange={(event) => {
                    setSelectedRunId(event.target.value);
                    invalidate();
                  }}
                >
                  {runs.map((item) => (
                    <option key={item.id} value={item.id}>
                      {date(item.created_at, locale)} · {item.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {!history.loading && !run && <p>{t("trainingNoRuns")}</p>}
            {run && (
              <>
                <p className="muted">
                  {t("trainingSource", { id: run.version_id })}
                </p>
                <TrainingReportView report={run.report} />
                <section
                  className="training-dry-run"
                  aria-label={t("trainingDryRun")}
                >
                  <h3>{t("trainingDryRun")}</h3>
                  <p>{t("trainingDryRunHint")}</p>
                  <dl>
                    <dt>{t("trainingLedger")}</dt>
                    <dd>
                      <code>{run.ledger_sha256}</code>
                    </dd>
                  </dl>
                  <a
                    className="text-button"
                    href={`/api/training-governance/${encodeURIComponent(run.id)}/ledger`}
                    download
                  >
                    {t("trainingDownloadLedger")}
                  </a>
                  {run.cleaned_version_id ? (
                    <p role="status">
                      {t("trainingCleanedVersion", {
                        id: run.cleaned_version_id,
                      })}
                    </p>
                  ) : (
                    <button
                      type="button"
                      className="button"
                      disabled={busy}
                      onClick={() => {
                        void clean();
                      }}
                    >
                      {t("trainingReviewClean")}
                    </button>
                  )}
                </section>
              </>
            )}
            {plan && (
              <PlanCard
                plan={plan}
                onOpenReceipt={(target) => {
                  window.location.hash = lineageHref(target);
                }}
                onInvalidated={() => {
                  setPlan(null);
                }}
                onResolved={(result) => {
                  if (result === null) setPlan(null);
                  if (result?.status === "SUCCEEDED") {
                    setLatest(null);
                    setCompleted(true);
                    history.reload();
                    onChanged();
                  }
                }}
              />
            )}
            {completed && <p role="status">{t("trainingCleanReady")}</p>}
          </>
        )
      )}
    </details>
  );
}
