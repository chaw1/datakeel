import { useI18n } from "../../i18n/useI18n";

import { stateMessages } from "./model";
import { LeaseBoard } from "./team/LeaseBoard";
import { SkillDispatch } from "./team/SkillDispatch";
import { TeamPackages } from "./team/TeamPackages";

import type { ProjectWorkbench } from "../../api/production";

export function ProjectCockpit({
  data,
  can = () => false,
  onChanged = () => undefined,
}: {
  data: ProjectWorkbench;
  can?: (scope: string) => boolean;
  onChanged?: () => void;
}) {
  const { t } = useI18n();
  const team = data.project.workflow_tier === "team";
  return (
    <div className="wb-cockpit">
      {team && (
        <TeamPackages
          data={data}
          canAccept={can("production:accept")}
          onChanged={onChanged}
        />
      )}
      {team && can("production:assign") && (
        <SkillDispatch
          key={data.tasks.map((task) => `${task.id}:${task.state}`).join()}
          data={data}
          onChanged={onChanged}
        />
      )}
      {team && (
        <LeaseBoard
          data={data}
          canRevoke={can("production:assign")}
          onChanged={onChanged}
        />
      )}
      <section className="card">
        <h2>{t("wbProgress")}</h2>
        <dl className="wb-counts">
          <div>
            <dt>{t("wbTotal")}</dt>
            <dd>{data.progress.total}</dd>
          </div>
          {data.progress.counts.map(({ state, count }) => (
            <div key={state}>
              <dt>{t(stateMessages[state])}</dt>
              <dd>{count}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section className="card">
        <h2>{t("wbQuality")}</h2>
        <p>{t("wbTaskCount", { count: data.agreement.sample_count })}</p>
        {data.agreement.boxes.length > 0 && (
          <>
            <h3>{t("wbBoxAgreement")}</h3>
            <ul>
              {data.agreement.boxes.map((pair) => (
                <li key={`${pair.annotator_a}:${pair.annotator_b}`}>
                  {pair.annotator_a} / {pair.annotator_b}:{" "}
                  {pair.mean_iou == null
                    ? t("wbUnavailable")
                    : pair.mean_iou.toFixed(3)}
                </li>
              ))}
            </ul>
          </>
        )}
        {data.agreement.classification.pairs.length > 0 && (
          <>
            <h3>{t("wbClassificationAgreement")}</h3>
            <ul>
              {data.agreement.classification.pairs.map((pair) => (
                <li key={`${pair.annotator_a}:${pair.annotator_b}`}>
                  {pair.annotator_a} / {pair.annotator_b}:{" "}
                  {pair.cohen_kappa.value == null
                    ? t("wbUnavailable")
                    : pair.cohen_kappa.value.toFixed(3)}
                </li>
              ))}
            </ul>
          </>
        )}
        {!data.agreement.boxes.length &&
          !data.agreement.classification.pairs.length && (
            <p className="muted">{t("wbNoAgreement")}</p>
          )}
        <p>{t("wbRepeatedRework")}</p>
        {data.progress.rework_task_ids.length ? (
          <ul>
            {data.progress.rework_task_ids.map((id) => {
              const sample = data.task_samples.find(
                (item) => item.task_id === id,
              );
              return (
                <li key={id} title={sample?.path}>
                  {sample?.name ?? t("wbUnnamedSample")}
                </li>
              );
            })}
          </ul>
        ) : (
          <p>{t("wbNoRepeatedRework")}</p>
        )}
      </section>
      <section className="card">
        <h2>{t("wbPeople")}</h2>
        <div className="table-wrap">
          <table aria-label={t("wbPeople")}>
            <thead>
              <tr>
                <th>{t("wbAnnotator")}</th>
                <th>{t("wbAssigned")}</th>
                <th>{t("wbCompleted")}</th>
                <th>{t("wbReviewCount")}</th>
                <th>{t("wbReworkRate")}</th>
              </tr>
            </thead>
            <tbody>
              {data.workload.annotators.map((person) => (
                <tr key={person.actor}>
                  <td>{person.actor}</td>
                  <td>{person.assigned}</td>
                  <td>{person.completed}</td>
                  <td>{person.review_count}</td>
                  <td>{`${String(Math.round(person.rework_rate * 100))}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card">
        <h2>{t("wbPrelabels")}</h2>
        <dl className="wb-counts">
          {data.confidence.buckets.map((bucket) => (
            <div key={bucket.lower}>
              <dt>{`${String(bucket.lower)} – ${String(bucket.upper)}`}</dt>
              <dd>{bucket.count}</dd>
            </div>
          ))}
        </dl>
        <h3>{t("wbPrelabelAccuracy")}</h3>
        <p>
          {data.prelabel_accuracy.exact_match_rate == null
            ? t("wbUnavailable")
            : `${String(Math.round(data.prelabel_accuracy.exact_match_rate * 100))}%`}
        </p>
        <p>
          {t("wbPrelabelReference", {
            matched: data.prelabel_accuracy.exact_match_tasks,
            assessed: data.prelabel_accuracy.assessed_tasks,
          })}
        </p>
      </section>
    </div>
  );
}
