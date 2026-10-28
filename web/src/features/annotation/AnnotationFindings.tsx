import { annotationPath } from "../../api/annotation";
import { useI18n } from "../../i18n/useI18n";

import type { AnnotationReport } from "../../api/annotation";
import type { MessageKey } from "../../i18n/en";

type FindingCode = AnnotationReport["result"]["findings"][number]["code"];
const ruleLabels: Record<FindingCode, MessageKey> = {
  minority_label: "annotationMinority",
  near_duplicate_conflict: "annotationDuplicate",
  bbox_size_outlier: "annotationBoxSize",
  bbox_aspect_outlier: "annotationBoxAspect",
  invalid_bbox: "annotationInvalidBox",
  multilabel_conflict: "annotationMultilabel",
  invalid_span: "annotationInvalidSpan",
  bbox_category_minority: "annotationBoxCategory",
  bbox_missing: "annotationBoxMissing",
  bbox_extra: "annotationBoxExtra",
  duplicate_bbox: "annotationBoxDuplicate",
  span_category_minority: "annotationSpanCategory",
  span_boundary_minority: "annotationSpanBoundary",
  span_missing: "annotationSpanMissing",
  span_extra: "annotationSpanExtra",
  duplicate_span: "annotationSpanDuplicate",
  span_length_outlier: "annotationSpanLength",
  rare_category: "annotationRareCategory",
};

export function AnnotationFindings({ report }: { report: AnnotationReport }) {
  const { t } = useI18n();
  const findings = report.result.findings;
  const comparison = report.comparison;
  const path = `${annotationPath(report.dataset_id)}/rework/${encodeURIComponent(report.id)}`;
  return (
    <>
      <section className="card">
        <div className="card-heading">
          <h3>
            {t("annotationFindings")} · {findings.length}
          </h3>
          <div className="export-actions">
            <a className="button" href={`${path}?format=json`} download>
              {t("annotationExportJson")}
            </a>
            <a className="button" href={`${path}?format=csv`} download>
              {t("annotationExportCsv")}
            </a>
          </div>
        </div>
        <p>{t("annotationFindingsHint")}</p>
        {!findings.length ? (
          <p>{t("annotationNoFindings")}</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("annotationSample")}</th>
                  <th>{t("annotationAnnotator")}</th>
                  <th>{t("annotationCode")}</th>
                  <th>{t("annotationReason")}</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((finding) => (
                  <tr key={finding.finding_id}>
                    <td>
                      <code>{finding.sample_id}</code>
                    </td>
                    <td>{finding.annotator_id}</td>
                    <td>{t(ruleLabels[finding.code])}</td>
                    <td>
                      {finding.reason}
                      <ul>
                        {finding.evidence.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="card">
        <h3>{t("annotationRework")}</h3>
        {comparison ? (
          <dl className="annotation-statistics">
            <div>
              <dt>{t("annotationCorrected")}</dt>
              <dd>{comparison.corrected_count}</dd>
            </div>
            <div>
              <dt>{t("annotationIntroduced")}</dt>
              <dd>{comparison.introduced_count}</dd>
            </div>
            <div>
              <dt>{t("annotationRemaining")}</dt>
              <dd>{comparison.remaining_count}</dd>
            </div>
            <div>
              <dt>{t("annotationUnassessed")}</dt>
              <dd>{comparison.unassessed_count}</dd>
            </div>
            <div>
              <dt>{t("annotationChangedRecords")}</dt>
              <dd>{comparison.changed_records}</dd>
            </div>
            <div>
              <dt>{t("annotationAddedRemoved")}</dt>
              <dd>
                {comparison.added_records} / {comparison.removed_records}
              </dd>
            </div>
            <div>
              <dt>{t("annotationInspectionDefects")}</dt>
              <dd>
                {comparison.inspection_defects_changed} /{" "}
                {comparison.inspection_defects}
              </dd>
            </div>
          </dl>
        ) : (
          <p>{t("annotationNoRework")}</p>
        )}
      </section>
    </>
  );
}
