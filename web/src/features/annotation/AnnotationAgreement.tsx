import { useI18n } from "../../i18n/useI18n";

import { AnnotationConfusion } from "./AnnotationConfusion";

import type { AnnotationResult } from "../../api/annotation";

function metric(value: number | null | undefined) {
  return value == null ? "—" : value.toFixed(4);
}

export function AnnotationAgreement({ result }: { result: AnnotationResult }) {
  const { t } = useI18n();
  const classification = result.classification;
  return (
    <section className="card annotation-agreement">
      <h3>{t("annotationAgreement")}</h3>
      <dl className="annotation-statistics">
        <div>
          <dt>{t("annotationSamples")}</dt>
          <dd>{result.sample_count}</dd>
        </div>
        <div>
          <dt>{t("annotationAnnotators")}</dt>
          <dd>{result.annotator_count}</dd>
        </div>
        <div>
          <dt>{t("annotationFleiss")}</dt>
          <dd title={classification.fleiss_kappa.reason ?? undefined}>
            {metric(classification.fleiss_kappa.value)}
          </dd>
        </div>
        <div>
          <dt>{t("annotationAlpha")}</dt>
          <dd title={classification.krippendorff_alpha.reason ?? undefined}>
            {metric(classification.krippendorff_alpha.value)}
          </dd>
        </div>
      </dl>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t("annotationPair")}</th>
              <th>{t("annotationCohen")}</th>
              <th>{t("annotationObserved")}</th>
            </tr>
          </thead>
          <tbody>
            {classification.pairs.map((pair) => (
              <tr key={`${pair.annotator_a}:${pair.annotator_b}`}>
                <td>
                  {pair.annotator_a} / {pair.annotator_b}
                </td>
                <td title={pair.cohen_kappa.reason ?? undefined}>
                  {metric(pair.cohen_kappa.value)}
                </td>
                <td>{metric(pair.cohen_kappa.observed_agreement)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <AnnotationConfusion pairs={classification.pairs} />
      {!!result.boxes.length && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("annotationPair")}</th>
                <th>{t("annotationBoxMatch")}</th>
                <th>{t("annotationMeanIou")}</th>
                <th>{t("annotationCategoryMatch")}</th>
              </tr>
            </thead>
            <tbody>
              {result.boxes.map((pair) => (
                <tr key={`${pair.annotator_a}:${pair.annotator_b}`}>
                  <td>
                    {pair.annotator_a} / {pair.annotator_b}
                  </td>
                  <td>{metric(pair.match_rate)}</td>
                  <td>{metric(pair.mean_iou)}</td>
                  <td>{metric(pair.category_agreement)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!!result.spans.length && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("annotationPair")}</th>
                <th>{t("annotationSpanExact")}</th>
                <th>{t("annotationSpanOverlap")}</th>
              </tr>
            </thead>
            <tbody>
              {result.spans.map((pair) => (
                <tr key={`${pair.annotator_a}:${pair.annotator_b}`}>
                  <td>
                    {pair.annotator_a} / {pair.annotator_b}
                  </td>
                  <td>{metric(pair.exact_f1)}</td>
                  <td>{metric(pair.overlap_f1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
