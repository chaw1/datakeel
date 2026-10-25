import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";

import { KGBadge } from "./KGBadge";
import { KGTranscriptions } from "./KGTranscriptions";
import { proposalLabels } from "./labels";

import type { KGRun } from "../../api/kg";

export function KGReports({
  runs,
  proposalsOnly = false,
}: {
  runs: KGRun[];
  proposalsOnly?: boolean;
}) {
  const { t, locale } = useI18n();
  const metrics = [
    ["documents", "kgDocuments"],
    ["blocks", "kgBlocks"],
    ["cached", "kgCached"],
    ["extracted", "kgExtracted"],
    ["failed", "kgFailedBlocks"],
    ["unexecuted", "kgUnexecuted"],
    ["model_calls", "kgModelCalls"],
    ["entities", "kgEntities"],
    ["relations", "kgRelations"],
    ["verified", "kgVerified"],
    ["needs_review", "kgNeedsReview"],
    ["input_tokens", "kgInputTokens"],
    ["output_tokens", "kgOutputTokens"],
  ] as const;
  if (proposalsOnly)
    return (
      <section>
        <p>{t("kgProposalIntro")}</p>
        {!runs.some((run) => run.report?.proposals.length) && (
          <p>{t("kgNoProposals")}</p>
        )}
        {runs.map((run) =>
          (run.report?.proposals ?? []).map((proposal, index) => (
            <details className="kg-report" key={`${run.id}:${String(index)}`}>
              <summary>
                {t(proposalLabels[proposal.reason])} · {t("kgCount")}:{" "}
                {proposal.count} · {run.profile_id}
              </summary>
              {!!proposal.entity_samples.length && (
                <ul>
                  {proposal.entity_samples.map((entity, at) => (
                    <li key={at}>
                      {entity.name} · {entity.type}
                    </li>
                  ))}
                </ul>
              )}
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{t("kgHead")}</th>
                      <th>{t("kgPredicate")}</th>
                      <th>{t("kgTail")}</th>
                      <th>{t("kgEvidence")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {proposal.samples.map((sample, at) => (
                      <tr key={at}>
                        <td>{sample.head}</td>
                        <td>{sample.relation}</td>
                        <td>{sample.tail}</td>
                        <td>{sample.evidence}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )),
        )}
      </section>
    );
  return (
    <section>
      {!runs.length && <p>{t("kgNoRuns")}</p>}
      {runs.map((run) => (
        <details className="kg-report" key={run.id}>
          <summary>
            <span>
              {date(run.created_at, locale)} · {run.profile_id} · {run.model}
            </span>
            <KGBadge value={run.status} />
          </summary>
          {run.report?.error && (
            <p className="error-banner" role="alert">
              {run.report.error}
            </p>
          )}
          <dl className="kg-metrics">
            {metrics.map(([field, label]) => (
              <div key={field}>
                <dt>{t(label)}</dt>
                <dd>{run.report?.[field] ?? 0}</dd>
              </div>
            ))}
            <div>
              <dt>{t("kgCost")}</dt>
              <dd>
                {run.report?.cost_usd == null
                  ? t("kgUnknown")
                  : Number(run.report.cost_usd).toFixed(6)}
              </dd>
            </div>
            <div>
              <dt>{t("kgElapsed")}</dt>
              <dd>{(run.report?.elapsed_seconds ?? 0).toFixed(2)}</dd>
            </div>
          </dl>
          <KGTranscriptions report={run.report} />
          {!!run.report?.partial_documents.length && (
            <>
              <h4>{t("kgPartialDocuments")}</h4>
              <ul>
                {run.report.partial_documents.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            </>
          )}
          {!!run.report?.failures.length && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("kgSource")}</th>
                    <th>{t("kgEvidence")}</th>
                    <th>{t("kgFailureReason")}</th>
                  </tr>
                </thead>
                <tbody>
                  {run.report.failures.map((failure, index) => (
                    <tr key={index}>
                      <td>{failure.filename}</td>
                      <td>
                        {t("kgOffsets", {
                          start: failure.start,
                          end: failure.end,
                        })}
                      </td>
                      <td>
                        {failure.reason}
                        {!failure.attempted ? ` · ${t("kgUnexecuted")}` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted">
            <code>{run.id}</code> · {run.extractor}
          </p>
        </details>
      ))}
    </section>
  );
}
