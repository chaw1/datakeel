import { useEffect, useState } from "react";

import { getTaskSamples, readProduction } from "../../../api/production";
import { useI18n } from "../../../i18n/useI18n";
import { actionMessage, actionProblem } from "../actionErrors";
import { executeProduction, prepareProduction } from "../actions";

import { needsApproval, PlanSigner } from "./PlanSigner";

import type {
  Assignment,
  LeaseStatus,
  ProjectWorkbench,
} from "../../../api/production";
import type { ActionPlan } from "../../../api/types";

function minutes(seconds: number) {
  return Math.max(0, Math.ceil(seconds / 60));
}

/** Live team leases from `lease_status`; managers can take a task back from its holder. */
export function LeaseBoard({
  data,
  canRevoke,
  onChanged,
}: {
  data: ProjectWorkbench;
  canRevoke: boolean;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [status, setStatus] = useState<LeaseStatus | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [target, setTarget] = useState<Assignment | null>(null);
  const [reason, setReason] = useState("");
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(false);
  const [reads, setReads] = useState(0);
  const projectId = data.project.id;
  useEffect(() => {
    const request = { live: true };
    // A function call, so the check after the await is not narrowed away.
    const alive = () => request.live;
    void readProduction<LeaseStatus>("lease_status", { project_id: projectId })
      .then(async (value) => {
        if (!alive()) return;
        setStatus(value);
        const ids = [...value.active, ...value.overdue].map(
          (item) => item.assignment.task_id,
        );
        if (!ids.length) return;
        const samples = await getTaskSamples(projectId, ids);
        if (alive())
          setNames(
            Object.fromEntries(
              samples.items.map((item) => [item.task_id, item.name]),
            ),
          );
      })
      .catch((failure: unknown) => {
        if (alive()) setError(actionMessage(failure, t, t("wbError")));
      });
    return () => {
      request.live = false;
    };
  }, [data, projectId, reads, t]);
  const name = (id: string) => names[id] ?? t("wbUnnamedSample");
  async function prepare(assignment: Assignment) {
    setBusy(true);
    setError("");
    setRetry(false);
    try {
      setPlan(
        await prepareProduction("revoke_assignment", {
          task_id: assignment.task_id,
          stage: assignment.stage,
          reason: reason.trim(),
        }),
      );
    } catch (failure) {
      setError(actionMessage(failure, t, t("wbError")));
    } finally {
      setBusy(false);
    }
  }
  async function sign() {
    if (!plan) return;
    setBusy(true);
    setError("");
    try {
      await executeProduction(plan, needsApproval(plan));
      setPlan(null);
      setTarget(null);
      setReason("");
      setReads((count) => count + 1);
      onChanged();
    } catch (failure) {
      setPlan(null);
      setRetry(actionProblem(failure) === "changed");
      setError(actionMessage(failure, t, t("wbError")));
    } finally {
      setBusy(false);
    }
  }
  const leases = status ? [...status.active, ...status.overdue] : [];
  return (
    <section className="card wb-leases">
      <h2>{t("wbLeases")}</h2>
      {!leases.length ? (
        <p className="muted">{t("wbNoLeases")}</p>
      ) : (
        <div className="table-wrap">
          <table aria-label={t("wbLeases")}>
            <thead>
              <tr>
                <th>{t("wbSample")}</th>
                <th>{t("wbHolder")}</th>
                <th>{t("wbLeaseLeft")}</th>
                {canRevoke && <th>{t("wbActions")}</th>}
              </tr>
            </thead>
            <tbody>
              {leases.map(({ assignment, seconds_remaining }) => (
                <tr key={assignment.id} data-assignment-id={assignment.id}>
                  <td>{name(assignment.task_id)}</td>
                  <td>{assignment.actor}</td>
                  <td>
                    {t("wbMinutesLeft", { count: minutes(seconds_remaining) })}
                  </td>
                  {canRevoke && (
                    <td>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          setTarget(assignment);
                          setPlan(null);
                          setError("");
                        }}
                      >
                        {t("wbRevoke")}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {target && !plan && (
        <div className="wb-revoke">
          <label>
            {t("wbRevokeReason", {
              name: name(target.task_id),
              actor: target.actor,
            })}
            <input
              type="text"
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
              }}
            />
          </label>
          <button
            type="button"
            className="button primary"
            disabled={busy || !reason.trim()}
            onClick={() => {
              void prepare(target);
            }}
          >
            {retry ? t("wbRedoAction") : t("wbPrepareRevoke")}
          </button>
        </div>
      )}
      {target && plan && (
        <PlanSigner
          title={t("wbRevokePlan")}
          plan={plan}
          busy={busy}
          signLabel={t("wbSignRevoke")}
          onCancel={() => {
            setPlan(null);
          }}
          onSign={() => {
            void sign();
          }}
        >
          <p>
            {t("wbRevokePlanText", {
              name: name(target.task_id),
              actor: target.actor,
            })}
          </p>
        </PlanSigner>
      )}
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </section>
  );
}
