import { useEffect, useState } from "react";

import { getAssignees, readProduction } from "../../../api/production";
import { useI18n } from "../../../i18n/useI18n";
import { actionMessage } from "../actionErrors";
import { executeProduction, prepareProduction } from "../actions";

import { planHandovers } from "./handovers";
import { needsApproval, PlanSigner } from "./PlanSigner";

import type {
  LeaseStatus,
  ProjectWorkbench,
  WorkbenchAssignees,
} from "../../../api/production";
import type { ActionPlan } from "../../../api/types";

type Person = WorkbenchAssignees["people"][number];

/** Undispatched tasks on this page and the registered people who may annotate them. */
function useAssignable(
  data: ProjectWorkbench,
  onError: (text: string) => void,
) {
  const { t } = useI18n();
  const projectId = data.project.id;
  const [people, setPeople] = useState<readonly Person[] | null>(null);
  const [held, setHeld] = useState<readonly string[]>([]);
  useEffect(() => {
    const request = { live: true };
    // A function call, so the check after the await is not narrowed away.
    const alive = () => request.live;
    void Promise.all([
      getAssignees(projectId, "annotation"),
      readProduction<LeaseStatus>("lease_status", { project_id: projectId }),
    ])
      .then(([listed, leases]) => {
        if (!alive()) return;
        setPeople(listed.people);
        setHeld(
          [...leases.active, ...leases.overdue].map(
            (item) => item.assignment.task_id,
          ),
        );
      })
      .catch((failure: unknown) => {
        if (alive()) onError(actionMessage(failure, t, t("wbError")));
      });
    return () => {
      request.live = false;
    };
  }, [data, projectId, onError, t]);
  const open = data.tasks.filter(
    (task) => task.state === "pending" && !held.includes(task.id),
  );
  return { people, open };
}

/** Hand chosen undispatched tasks to one registered person by name, then sign the plan. */
export function NamedDispatch({
  data,
  onChanged,
}: {
  data: ProjectWorkbench;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [error, setError] = useState("");
  const { people, open } = useAssignable(data, setError);
  const openIds = open.map((task) => task.id);
  const basis = openIds.join("\n");
  const [choice, setChoice] = useState({ basis, ids: openIds });
  if (choice.basis !== basis) setChoice({ basis, ids: openIds });
  const selected = choice.basis === basis ? choice.ids : openIds;
  const [actor, setActor] = useState("");
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const person = people?.find((item) => item.actor === actor);
  const name = (id: string) =>
    data.task_samples.find((item) => item.task_id === id)?.name ??
    t("wbUnnamedSample");
  async function run(step: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await step();
    } catch (reason) {
      setPlan(null);
      setError(actionMessage(reason, t, t("wbError")));
    } finally {
      setBusy(false);
    }
  }
  const prepare = () =>
    run(async () => {
      setPlan(
        await prepareProduction("assign_tasks", {
          task_ids: selected,
          actor,
          stage: "annotation",
        }),
      );
    });
  const sign = (signed: ActionPlan) =>
    run(async () => {
      await executeProduction(signed, needsApproval(signed));
      setPlan(null);
      onChanged();
    });
  return (
    <section
      className="card wb-named-dispatch"
      aria-label={t("wbNamedDispatch")}
    >
      <h2>{t("wbNamedDispatch")}</h2>
      {people && !people.length && (
        <p className="muted">{t("wbNoAssignees")}</p>
      )}
      {people && people.length > 0 && !open.length && (
        <p className="muted">{t("wbNothingToDispatch")}</p>
      )}
      {people && people.length > 0 && open.length > 0 && (
        <fieldset disabled={busy || !!plan}>
          <legend>{t("wbDispatchTasks", { count: selected.length })}</legend>
          {open.map((task) => (
            <label key={task.id} className="wb-attribute-check">
              <input
                type="checkbox"
                checked={selected.includes(task.id)}
                onChange={(event) => {
                  setChoice({
                    basis,
                    ids: event.target.checked
                      ? [...selected, task.id]
                      : selected.filter((id) => id !== task.id),
                  });
                }}
              />
              {name(task.id)}
            </label>
          ))}
          <label>
            {t("wbAssignTo")}
            <select
              value={actor}
              onBlur={(event) => {
                setActor(event.target.value);
              }}
              onChange={(event) => {
                setActor(event.target.value);
              }}
            >
              <option value="">{t("wbChoosePerson")}</option>
              {people.map((item) => (
                <option key={item.actor} value={item.actor}>
                  {item.display_name === item.actor
                    ? t("wbAssigneeOptionPlain", {
                        actor: item.actor,
                        count: item.current,
                      })
                    : t("wbAssigneeOption", {
                        name: item.display_name,
                        actor: item.actor,
                        count: item.current,
                      })}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="button primary"
            disabled={!selected.length || !actor}
            onClick={() => void prepare()}
          >
            {t("wbPrepareAssign")}
          </button>
        </fieldset>
      )}
      {plan && (
        <PlanSigner
          title={t("wbAssignPlan")}
          plan={plan}
          busy={busy}
          signLabel={t("wbSignAssign")}
          onCancel={() => {
            setPlan(null);
          }}
          onSign={() => void sign(plan)}
        >
          <p>
            {t("wbAssignPlanText", {
              count: selected.length,
              name: person?.display_name ?? actor,
            })}
          </p>
          {planHandovers(plan).map((item) => (
            <p key={item.task_id}>
              {t("wbReworkHandover", {
                name: name(item.task_id),
                round: item.round,
                from: item.from_actor,
                to: item.to_actor,
              })}
            </p>
          ))}
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
