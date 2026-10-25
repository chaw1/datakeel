import { useI18n } from "../../i18n/useI18n";

import type { KGEvaluation } from "../../api/kg";

export function KGImageEvaluations({ run }: { run: KGEvaluation }) {
  const { t } = useI18n();
  if (!run.image_recording && !run.image_product) return null;
  const groupLabels = {
    A_clean: "kgImageClean",
    A_scan: "kgImageScan",
    B: "kgImageDiagram",
    zh: "kgChinese",
    en: "kgEnglish",
  } as const;
  return (
    <section className="kg-image-evaluation">
      <h4>{t("kgImageEvaluation")}</h4>
      <p>
        {t("kgTranscriptionProfile")}: {run.transcription_profile}
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t("kgScoringView")}</th>
              <th>{t("kgSample")}</th>
              <th>{t("kgF1")}</th>
              <th>{t("kgPairF1")}</th>
              <th>{t("kgTraps")}</th>
              <th>{t("kgBoxHitRate")}</th>
              <th>{t("kgCER")}</th>
              <th>{t("kgIdentifierPreservation")}</th>
              <th>{t("kgTranscriptionFailed")}</th>
            </tr>
          </thead>
          <tbody>
            {(
              [
                ["kgRecorded", run.image_recording],
                ["kgProduct", run.image_product],
              ] as const
            ).flatMap(([label, view]) =>
              (view?.groups ?? []).map((group) => (
                <tr key={`${label}:${group.name}`}>
                  <td>{t(label)}</td>
                  <td>
                    {group.name in groupLabels
                      ? t(groupLabels[group.name as keyof typeof groupLabels])
                      : group.name}
                  </td>
                  <td>{group.metrics.relation_strict.f1.toFixed(3)}</td>
                  <td>{group.metrics.relation_pair.f1.toFixed(3)}</td>
                  <td>{group.metrics.trap_hits}</td>
                  <td>{(group.box_hit_rate * 100).toFixed(1)}%</td>
                  <td>
                    {group.cer == null
                      ? "—"
                      : `${(group.cer * 100).toFixed(2)}%`}
                  </td>
                  <td>
                    {group.identifier_preservation == null
                      ? "—"
                      : `${(group.identifier_preservation * 100).toFixed(1)}%`}
                  </td>
                  <td>{group.transcription_failures}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
