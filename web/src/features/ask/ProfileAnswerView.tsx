import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { objectHref } from "../object/navigation";

import type { AskAnswer } from "../../api/ask";

export function ProfileAnswerView({
  answer,
  onChooseDataset,
}: {
  answer: AskAnswer;
  onChooseDataset?: (id: string) => void;
}) {
  const { t, locale } = useI18n();
  const isComposing = useCompositionGuard();
  const profile = answer.profile;
  if (!profile) return null;
  const dataset = profile.dataset;
  return (
    <section className="ask-result" aria-label={t("askProfileTitle")}>
      <h2>{t("askProfileTitle")}</h2>
      <p>{answer.message}</p>
      {dataset && (
        <p>
          <a href={objectHref({ kind: "dataset", id: dataset.dataset_id })}>
            {dataset.dataset_name}
          </a>{" "}
          ·{" "}
          <a
            href={objectHref({
              kind: "version",
              id: dataset.version_id,
              datasetId: dataset.dataset_id,
              tab: "facts",
            })}
          >
            {t("askProfilePublishedVersion")}
          </a>
        </p>
      )}
      {answer.status === "answered" && (
        <>
          <p>
            {t(
              profile.sort_by === "gap_count"
                ? "askProfileSortCount"
                : "askProfileSortDuration",
            )}
          </p>
          <p>{t("askProfileScope")}</p>
          <div className="ask-table-scroll">
            <table>
              <caption>{t("askProfileRanking")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("askProfileDevice")}</th>
                  <th scope="col">{t("askProfileCount")}</th>
                  <th scope="col">{t("askProfileDuration")}</th>
                </tr>
              </thead>
              <tbody>
                {profile.ranking.map((rank) => (
                  <tr key={rank.device}>
                    <th scope="row">{rank.device}</th>
                    <td>{rank.interval_count}</td>
                    <td>
                      {new Intl.NumberFormat(locale, {
                        maximumFractionDigits: 3,
                      }).format(rank.total_gap_ms / 1000)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>{t("askProfileIntervals")}</h3>
          <p>{t("askProfileCoordinates")}</p>
          {profile.ranking.map((rank) => (
            <details key={rank.device}>
              <summary>{rank.device}</summary>
              <ul>
                {rank.evidence.map((item) => (
                  <li
                    key={`${item.file_id}:${String(item.start_ms)}:${String(item.end_ms)}`}
                  >
                    <a
                      href={objectHref({
                        kind: "file",
                        id: item.source_file_id,
                        datasetId: item.dataset_id,
                        versionId: item.source_version_id,
                        tab: "facts",
                      })}
                    >
                      {item.filename}
                    </a>{" "}
                    ·{" "}
                    <a
                      href={objectHref({
                        kind: "version",
                        id: item.source_version_id,
                        datasetId: item.dataset_id,
                        tab: "facts",
                      })}
                    >
                      {t("askProfileSourceVersion")}
                    </a>{" "}
                    · {item.time_column} · {t("askProfileRows")}:{" "}
                    {item.rows.join(", ")}
                    {" · "}
                    {new Date(item.start_ms).toISOString()} →{" "}
                    {new Date(item.end_ms).toISOString()}
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </>
      )}
      {answer.status === "clarification" && (
        <ul>
          {profile.candidates.map((item) => (
            <li key={item.dataset_id}>
              <button
                type="button"
                className="ask-candidate"
                onKeyDown={(event) => {
                  if (isComposing(event.nativeEvent)) event.preventDefault();
                }}
                onClick={() => {
                  if (!isComposing()) onChooseDataset?.(item.dataset_id);
                }}
              >
                {item.dataset_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
