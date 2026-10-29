import { useI18n } from "../../i18n/useI18n";

import { stateMessages } from "./model";

import type { ProjectWorkbench } from "../../api/production";

export function ProjectCockpit({ data }: { data: ProjectWorkbench }) {
  const { t } = useI18n();
  return (
    <div className="wb-cockpit">
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
        <p>{t("wbRepeatedRework")}</p>
        {data.progress.rework_task_ids.length ? (
          <ul>
            {data.progress.rework_task_ids.map((id) => (
              <li key={id}>
                <code>{id}</code>
              </li>
            ))}
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
                <th>{t("wbActor", { actor: "" })}</th>
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
