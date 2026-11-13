import { useEffect, useState } from "react";

import { get } from "../../api/client";
import { readChain, runChain } from "../../api/intents";
import { useI18n } from "../../i18n/useI18n";
import { ActionReceipt } from "../actions/ActionReceipt";
import { PlanCard } from "../actions/PlanCard";
import { approvalActions } from "../approvals/approvalActions";
import { money } from "../traces/format";

import { ChainReplanBar } from "./ChainReplanBar";
import { LabelDraftEditor } from "./LabelDraftEditor";

import type {
  ActionChain,
  ChainStep,
  IntentResult,
  PageContext,
} from "../../api/intents";
import type { ActionPlan, ActionRun } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";
import type { MessageKey } from "../../i18n/en";

const statusKeys: Record<ChainStep["status"], MessageKey> = {
  planned: "chainStepPlanned",
  running: "chainStepRunning",
  awaiting_approval: "chainStepWaiting",
  succeeded: "chainStepSucceeded",
  failed: "chainStepFailed",
};
const statusTones: Record<ChainStep["status"], string> = {
  planned: "gray",
  running: "amber",
  awaiting_approval: "amber",
  succeeded: "green",
  failed: "red",
};

// Action names are written to sit inside sentences ("Sign and publish label set").
function sentenceCase(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function useRuns(chain: ActionChain) {
  const wanted = chain.steps.flatMap((step) => step.run_ids ?? []);
  const key = wanted.join(",");
  const [runs, setRuns] = useState<ActionRun[]>([]);
  useEffect(() => {
    if (!key) return;
    let active = true;
    void get<ActionRun[]>("/api/actions/runs")
      .then((value) => {
        if (active)
          setRuns(value.filter((run) => key.split(",").includes(run.id)));
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [key]);
  return runs;
}

function useWaitingPlan(chain: ActionChain) {
  const step = chain.steps.find((item) => item.status === "awaiting_approval");
  const id = step?.plan_ids?.find(Boolean) ?? "";
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  useEffect(() => {
    if (!id) return;
    let active = true;
    void get<ActionPlan>(`/api/actions/plans/${encodeURIComponent(id)}`)
      .then((value) => {
        if (active) setPlan(value);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [id]);
  return plan?.id === id && plan.status === "PREPARED" ? plan : null;
}

export function ChainCard({
  initial,
  busy,
  hasContinuation = false,
  context,
  onReplanned,
  onResolved,
  onOpenReceipt,
}: {
  initial: ActionChain;
  busy: boolean;
  hasContinuation?: boolean;
  context?: PageContext;
  onReplanned?: (result: IntentResult) => void;
  onResolved: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t, locale } = useI18n();
  const [chain, setChain] = useState(initial);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const runs = useRuns(chain);
  const waiting = useWaitingPlan(chain);
  const id = initial.id ?? "";
  useEffect(() => {
    if (!id) return;
    let active = true;
    void readChain(id)
      .then((value) => {
        if (active) setChain(value);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [id]);
  async function advance() {
    if (running || busy || !id) return;
    setRunning(true);
    setError("");
    try {
      setChain(await runChain(id));
      onResolved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunning(false);
    }
  }
  const button: MessageKey | null =
    chain.status === "planned"
      ? "chainConfirm"
      : chain.status === "failed"
        ? "chainResume"
        : chain.status === "awaiting_approval" || chain.status === "running"
          ? "chainContinue"
          : null;
  return (
    <section className="chain-card" aria-label={t("chainTitle")}>
      <header>
        <strong>
          {t("chainTitle")} · {t("chainSteps", { count: chain.steps.length })}
        </strong>
        <span className={`badge ${statusTones[chain.status]}`}>
          {t(statusKeys[chain.status])}
        </span>
      </header>
      <ol className="chain-steps">
        {chain.steps.map((step) => {
          const estimate = step.estimate;
          const targets = Math.max(step.items?.length ?? 0, 1);
          return (
            <li key={step.id} data-status={step.status}>
              <div className="chain-step-head">
                <span>
                  {sentenceCase(t(approvalActions[step.action as never]))}
                </span>
                <span className={`badge ${statusTones[step.status]}`}>
                  {t(statusKeys[step.status])}
                </span>
              </div>
              <p className="chain-step-impact">
                {estimate?.object_count == null
                  ? t("chainCountUnknown")
                  : t("chainCount", { count: estimate.object_count })}
                {targets > 1 && <> · {t("chainTargets", { count: targets })}</>}
                {" · "}
                {estimate?.cost_usd
                  ? t("chainCost", { cost: money(estimate.cost_usd, locale) })
                  : t("chainFree")}
                {estimate?.requires_approval && (
                  <span className="badge amber">
                    {t("chainNeedsSignature")}
                  </span>
                )}
                {estimate?.external && (
                  <span className="badge amber">{t("chainExternal")}</span>
                )}
              </p>
              {!!step.details?.length && (
                <dl className="chain-step-details">
                  {step.details.map((detail) => (
                    <div
                      key={`${detail.label}:${detail.value}`}
                      data-tone={detail.tone}
                    >
                      <dt>{detail.label}</dt>
                      <dd>{detail.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {step.error && (
                <p className="error-text" role="alert">
                  {t("chainFailedBecause", { reason: step.error })}
                </p>
              )}
              {runs
                .filter((run) => step.run_ids?.includes(run.id))
                .map((run) => (
                  <ActionReceipt
                    key={run.id}
                    run={run}
                    onOpenReceipt={onOpenReceipt}
                  />
                ))}
              {step.action === "draft_label_set" &&
                step.status === "succeeded" &&
                typeof step.outputs?.label_set_id === "string" &&
                typeof step.outputs.label_set_version === "number" && (
                  <LabelDraftEditor
                    labelSetId={step.outputs.label_set_id}
                    version={step.outputs.label_set_version}
                    onPublished={onResolved}
                    onOpenReceipt={onOpenReceipt}
                  />
                )}
            </li>
          );
        })}
      </ol>
      {!!chain.notes?.length && (
        <ul className="chain-notes">
          {chain.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      {waiting && (
        <div className="chain-signature">
          <p>{t("chainSignatureHint")}</p>
          <PlanCard
            plan={waiting}
            readOnly={busy}
            onResolved={(run) => {
              if (run?.status === "SUCCEEDED") void advance();
            }}
            onInvalidated={onResolved}
            onOpenReceipt={onOpenReceipt}
          />
        </div>
      )}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {button ? (
        <div className="chain-actions">
          {chain.status === "planned" && (
            <p className="muted small">{t("chainNothingYet")}</p>
          )}
          <button
            className="button primary"
            disabled={running || busy}
            onClick={() => {
              void advance();
            }}
          >
            {t(button)}
          </button>
        </div>
      ) : (
        (!(chain.deferred_steps?.length ?? 0) || !onReplanned) && (
          <p role="status" className="chain-done">
            {t("chainAllDone")}
          </p>
        )
      )}
      {onReplanned && (
        <ChainReplanBar
          chain={chain}
          busy={busy}
          running={running}
          hasContinuation={hasContinuation}
          context={context}
          onReplanned={onReplanned}
          onError={setError}
        />
      )}
    </section>
  );
}
