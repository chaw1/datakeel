import { useState } from "react";

import { previewDispatch } from "../../../api/production";
import { useI18n } from "../../../i18n/useI18n";
import { actionMessage } from "../actionErrors";
import { executeProduction, prepareProduction } from "../actions";

import { needsApproval, PlanSigner } from "./PlanSigner";

import type {
  ProjectWorkbench,
  SkillDispatchPreview,
} from "../../../api/production";
import type { ActionPlan } from "../../../api/types";

const reasons: Record<string, Parameters<ReturnType<typeof useI18n>["t"]>[0]> =
  {
    task_state_not_dispatchable: "wbSkipState",
    already_assigned: "wbSkipAssigned",
    load_limit_reached: "wbSkipLoad",
    no_qualified_person: "wbSkipSkill",
  };

/** Pick tasks and a per-person cap, preview who gets what, then sign the dispatch plan. */
export function SkillDispatch({
  data,
  onChanged,
}: {
  data: ProjectWorkbench;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const open = data.tasks.filter((task) => task.state === "pending");
  const openIds = open.map((task) => task.id);
  const basis = openIds.join("\n");
  // Choices belong to one set of undispatched tasks; when it changes, start from all of them.
  const [choice, setChoice] = useState({ basis, ids: openIds });
  if (choice.basis !== basis) setChoice({ basis, ids: openIds });
  const selected = choice.basis === basis ? choice.ids : openIds;
  const setSelected = (ids: string[]) => {
    setChoice({ basis, ids });
  };
  const [cap, setCap] = useState("");
  const [preview, setPreview] = useState<SkillDispatchPreview | null>(null);
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const name = (id: string) =>
    data.task_samples.find((item) => item.task_id === id)?.name ??
    t("wbUnnamedSample");
  const limit = cap ? Number(cap) : null;
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
  const values = {
    task_ids: selected,
    stage: "annotation" as const,
    candidates: [],
    ...(limit ? { max_active_tasks: limit } : {}),
  };
  return (
    <section className="card wb-dispatch" aria-label={t("wbSkillDispatch")}>
      <h2>{t("wbSkillDispatch")}</h2>
      {!data.project.skill_requirement ? (
        <p className="muted">{t("wbSkillDispatchNeedsRequirement")}</p>
      ) : !open.length ? (
        <p className="muted">{t("wbNothingToDispatch")}</p>
      ) : (
        <fieldset disabled={busy || !!plan}>
          <legend>{t("wbDispatchTasks", { count: selected.length })}</legend>
          {open.map((task) => (
            <label key={task.id} className="wb-attribute-check">
              <input
                type="checkbox"
                checked={selected.includes(task.id)}
                onChange={(event) => {
                  setPreview(null);
                  setSelected(
                    event.target.checked
                      ? [...selected, task.id]
                      : selected.filter((id) => id !== task.id),
                  );
                }}
              />
              {name(task.id)}
            </label>
          ))}
          <label>
            {t("wbDispatchCap")}
            <input
              type="number"
              min={1}
              value={cap}
              placeholder={t("wbDispatchCapDefault")}
              onChange={(event) => {
                setPreview(null);
                setCap(event.target.value);
              }}
            />
          </label>
          <button
            type="button"
            disabled={!selected.length}
            onClick={() => {
              void run(async () => {
                setPreview(await previewDispatch(data.project.id, values));
              });
            }}
          >
            {t("wbPreviewDispatch")}
          </button>
        </fieldset>
      )}
      {preview && !plan && (
        <div className="wb-dispatch-preview">
          <table aria-label={t("wbDispatchPeople")}>
            <thead>
              <tr>
                <th>{t("wbAnnotator")}</th>
                <th>{t("wbDispatchCurrent")}</th>
                <th>{t("wbDispatchAdded")}</th>
              </tr>
            </thead>
            <tbody>
              {preview.people.map((person) => (
                <tr key={person.actor}>
                  <td>{person.actor}</td>
                  <td>{person.current}</td>
                  <td>{person.added}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {preview.unassigned.length > 0 && (
            <ul aria-label={t("wbDispatchUnassigned")}>
              {preview.unassigned.map((skip) => (
                <li key={skip.task_id}>
                  {t("wbDispatchSkipped", {
                    name: name(skip.task_id),
                    reason: t(reasons[skip.reason] ?? "wbSkipOther"),
                  })}
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            className="button primary"
            disabled={busy || !preview.picks.length}
            onClick={() => {
              void run(async () => {
                setPlan(
                  await prepareProduction("assign_tasks", {
                    ...values,
                    strategy: "skill",
                  }),
                );
              });
            }}
          >
            {t("wbPrepareDispatch")}
          </button>
        </div>
      )}
      {plan && preview && (
        <PlanSigner
          title={t("wbDispatchPlan")}
          plan={plan}
          busy={busy}
          signLabel={t("wbSignDispatch")}
          onCancel={() => {
            setPlan(null);
          }}
          onSign={() => {
            void run(async () => {
              await executeProduction(plan, needsApproval(plan));
              setPlan(null);
              setPreview(null);
              onChanged();
            });
          }}
        >
          <ul className="wb-plan-summary">
            {preview.people
              .filter((person) => person.added > 0)
              .map((person) => (
                <li key={person.actor}>
                  {t("wbDispatchPersonGets", {
                    actor: person.actor,
                    count: person.added,
                  })}
                </li>
              ))}
            <li>{t("wbDispatchLeft", { count: preview.unassigned.length })}</li>
          </ul>
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
