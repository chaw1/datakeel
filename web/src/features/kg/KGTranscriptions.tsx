import { useI18n } from "../../i18n/useI18n";

import type { KGRun } from "../../api/kg";

export function KGTranscriptions({ report }: { report: KGRun["report"] }) {
  const { t } = useI18n();
  if (!report?.transcriptions.length) return null;
  return (
    <section className="kg-transcriptions">
      <h4>{t("kgTranscriptions")}</h4>
      <dl className="kg-metrics">
        <div>
          <dt>{t("kgLocatedRelations")}</dt>
          <dd>{report.located_relations}</dd>
        </div>
        <div>
          <dt>{t("kgUnlocatedRelations")}</dt>
          <dd>{report.unlocated_relations}</dd>
        </div>
        <div>
          <dt>{t("kgTranscriptionFailed")}</dt>
          <dd>{report.transcription_failed}</dd>
        </div>
        <div>
          <dt>{t("kgCloudCalls")}</dt>
          <dd>{report.cloud_calls}</dd>
        </div>
        <div>
          <dt>{t("kgCloudCost")}</dt>
          <dd>
            {report.cloud_cost_usd == null
              ? t("kgUnknown")
              : Number(report.cloud_cost_usd).toFixed(6)}
          </dd>
        </div>
      </dl>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t("kgSource")}</th>
              <th>{t("kgTranscriptionRoute")}</th>
              <th>{t("kgModel")}</th>
              <th>{t("kgTranscriptionStatus")}</th>
              <th>{t("kgFailureReason")}</th>
            </tr>
          </thead>
          <tbody>
            {report.transcriptions.map((item) => (
              <tr key={item.file_id}>
                <td>{item.filename}</td>
                <td>
                  {item.backend} / {item.mode}
                </td>
                <td>{item.model}</td>
                <td>
                  {item.cached
                    ? t("kgTranscriptionCached")
                    : t(
                        item.status === "failed"
                          ? "kgFailed"
                          : item.status === "unexecuted"
                            ? "kgUnexecuted"
                            : "kgCompleted",
                      )}
                </td>
                <td>{item.error ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
