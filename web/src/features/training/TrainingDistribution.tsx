import { useI18n } from "../../i18n/useI18n";

import type { SplitSet } from "../../api/training";

export function TrainingDistribution({ split }: { split: SplitSet }) {
  const { t } = useI18n();
  const labels = [
    ...new Set(
      split.distributions.flatMap((item) =>
        item.labels.map((label) => label.label),
      ),
    ),
  ].sort();
  const rows = [null, ...labels];
  const ratios = split.request.ratios ?? { train: 0.8, val: 0.1, test: 0.1 };
  const hasEmptyRequestedSet =
    split.request.source === "generated" &&
    split.distributions.some(
      (item) => ratios[item.split] > 0 && item.count === 0,
    );
  return (
    <section aria-label={`${t("trainingDistribution")}: ${split.request.name}`}>
      <h4>{split.request.name}</h4>
      <p className="muted small">
        {t("trainingSummary", {
          count: split.members.length,
          seed: split.request.seed,
        })}
      </p>
      {hasEmptyRequestedSet && (
        <p className="muted small" role="status">
          {t("trainingEmptyRequestedSet")}
        </p>
      )}
      <div className="table-scroll">
        <table className="training-distribution">
          <caption>{t("trainingDistribution")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("trainingClass")}</th>
              {split.distributions.map((item) => (
                <th scope="col" key={item.split}>
                  {t(
                    item.split === "train"
                      ? "trainingTrain"
                      : item.split === "val"
                        ? "trainingVal"
                        : "trainingTest",
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((label) => (
              <tr key={label === null ? "total" : `label:${label}`}>
                <th scope="row">{label ?? t("trainingTotal")}</th>
                {split.distributions.map((item) => {
                  const count =
                    label === null
                      ? item.count
                      : (item.labels.find((entry) => entry.label === label)
                          ?.count ?? 0);
                  const total =
                    label === null ? split.members.length : item.count;
                  const share = total
                    ? ((100 * count) / total).toFixed(1)
                    : "0.0";
                  return (
                    <td key={item.split}>
                      <span>{t("trainingCountShare", { count, share })}</span>
                      <meter
                        className={`training-bar training-bar-${item.split}`}
                        min="0"
                        max={Math.max(1, total)}
                        value={count}
                        aria-label={t("trainingBar", {
                          label: label ?? t("trainingTotal"),
                          split: item.split,
                          count,
                          total,
                        })}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
