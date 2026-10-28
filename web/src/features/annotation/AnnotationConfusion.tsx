import { useI18n } from "../../i18n/useI18n";

import type { AnnotationResult } from "../../api/annotation";

type Pair = AnnotationResult["classification"]["pairs"][number];

export function AnnotationConfusion({ pairs }: { pairs: Pair[] }) {
  const { t } = useI18n();
  const shown = pairs.filter((pair) => pair.categories.length);
  if (!shown.length) return null;
  return (
    <details className="annotation-confusion">
      <summary>{t("annotationConfusion")}</summary>
      <p>{t("annotationMatrixHint")}</p>
      {shown.map((pair) => (
        <div key={`${pair.annotator_a}:${pair.annotator_b}`}>
          <h4>
            {pair.annotator_a} / {pair.annotator_b}
          </h4>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">
                    {pair.annotator_a} \ {pair.annotator_b}
                  </th>
                  {pair.categories.map((category) => (
                    <th key={category} scope="col">
                      {category}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pair.categories.map((category, row) => (
                  <tr key={category}>
                    <th scope="row">{category}</th>
                    {pair.matrix[row].map((count, column) => (
                      <td key={pair.categories[column]}>{count}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </details>
  );
}
