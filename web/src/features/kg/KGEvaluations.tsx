import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useResource } from "../../lib/useResource";

import { KGImageEvaluations } from "./KGImageEvaluations";

import type { KGEvaluation } from "../../api/kg";

export function KGEvaluations() {
  const { t, locale } = useI18n();
  const resource = useResource<KGEvaluation[]>("/api/kg/evaluations");
  return (
    <section>
      <p>{t("kgEvaluationNote")}</p>
      <ResourceState {...resource} onRetry={resource.reload} />
      <button className="button" onClick={resource.reload}>
        {t("refreshHistory")}
      </button>
      <div className="table-scroll">
        <table className="kg-evaluations">
          <thead>
            <tr>
              <th>{t("kgCreated")}</th>
              <th>{t("kgProfile")}</th>
              <th>{t("kgModel")}</th>
              <th>
                {t("kgRecorded")} {t("kgF1")}
              </th>
              <th>
                {t("kgProduct")} {t("kgPRF")}
              </th>
              <th>
                {t("kgVerifiedOnly")} {t("kgF1")}
              </th>
              <th>{t("kgTraps")}</th>
            </tr>
          </thead>
          <tbody>
            {(resource.value ?? []).map((run) => (
              <tr key={run.id}>
                <td>{date(run.created_at ?? "", locale)}</td>
                <td>{run.profile}</td>
                <td>{run.model}</td>
                <td>{run.recording.all.relation_strict.f1.toFixed(3)}</td>
                <td>
                  {[
                    run.product.all.relation_strict.p,
                    run.product.all.relation_strict.r,
                    run.product.all.relation_strict.f1,
                  ]
                    .map((value) => value.toFixed(3))
                    .join(" / ")}
                </td>
                <td>{run.product.verified.relation_strict.f1.toFixed(3)}</td>
                <td>{run.product.all.trap_hits}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!resource.loading && !resource.value?.length && (
        <p>{t("kgNoEvaluations")}</p>
      )}
      {(resource.value ?? []).map((run) => (
        <details className="kg-report" key={run.id}>
          <summary>
            {t("kgEvaluationDetails")} · {run.profile} ·{" "}
            {date(run.created_at ?? "", locale)}
          </summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("kgSample")}</th>
                  <th>{t("kgPrecision")}</th>
                  <th>{t("kgRecall")}</th>
                  <th>{t("kgF1")}</th>
                  <th>{t("kgPairF1")}</th>
                  <th>{t("kgEntityF1")}</th>
                  <th>{t("kgTraps")}</th>
                  <th>{t("kgFailedBlocks")}</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ["kgRecorded", run.recording.all],
                    ["kgProduct", run.product.all],
                    ["kgVerifiedOnly", run.product.verified],
                    ["kgChinese", run.product.zh],
                    ["kgEnglish", run.product.en],
                  ] as const
                ).map(([label, metrics]) => (
                  <tr key={label}>
                    <td>{t(label)}</td>
                    <td>{metrics.relation_strict.p.toFixed(3)}</td>
                    <td>{metrics.relation_strict.r.toFixed(3)}</td>
                    <td>{metrics.relation_strict.f1.toFixed(3)}</td>
                    <td>{metrics.relation_pair.f1.toFixed(3)}</td>
                    <td>{metrics.entity_typed.f1.toFixed(3)}</td>
                    <td>{metrics.trap_hits}</td>
                    <td>{metrics.failed_blocks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <KGImageEvaluations run={run} />
          <dl className="kg-metrics">
            <div>
              <dt>{t("kgInputTokens")}</dt>
              <dd>{run.input_tokens}</dd>
            </div>
            <div>
              <dt>{t("kgOutputTokens")}</dt>
              <dd>{run.output_tokens}</dd>
            </div>
            <div>
              <dt>{t("kgCost")}</dt>
              <dd>
                {run.cost_usd == null
                  ? t("kgUnknown")
                  : Number(run.cost_usd).toFixed(6)}
              </dd>
            </div>
            <div>
              <dt>{t("kgElapsed")}</dt>
              <dd>{run.elapsed_seconds.toFixed(2)}</dd>
            </div>
            {(run.suite === "image"
              ? ([
                  ["transcription_cost_usd", "kgTranscriptionCost"],
                  ["extraction_cost_usd", "kgExtractionCost"],
                ] as const)
              : []
            ).map(([field, label]) => (
              <div key={field}>
                <dt>{t(label)}</dt>
                <dd>
                  {run[field] == null
                    ? t("kgUnknown")
                    : Number(run[field]).toFixed(6)}
                </dd>
              </div>
            ))}
          </dl>
        </details>
      ))}
    </section>
  );
}
