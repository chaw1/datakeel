import { useState } from "react";

import { Badge, Button } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";

import type { LeakageReport, SplitSet } from "../../api/training";
import type { FileItem, Version } from "../../api/types";

const signalLabel = {
  exact: "trainingExact",
  image: "trainingImage",
  text: "trainingText",
  group: "trainingGroupLeak",
} as const;
const splitLabel = {
  train: "trainingTrain",
  val: "trainingVal",
  test: "trainingTest",
} as const;
const pageSize = 8;
type Pair = LeakageReport["pairs"][number];

function groupPairs(pairs: Pair[]) {
  const groups = new Map<string, Pair[]>();
  for (const pair of pairs) {
    const key = JSON.stringify([pair.left_id, pair.right_id].sort());
    const signals = groups.get(key);
    if (signals) signals.push(pair);
    else groups.set(key, [pair]);
  }
  return [...groups.values()];
}

function FilePreview({
  datasetId,
  versionId,
  file,
}: {
  datasetId: string;
  versionId: string;
  file: FileItem;
}) {
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);
  if (file.modality !== "image" || failed)
    return <p className="delivery-preview-empty">{t("evNoImage")}</p>;
  return (
    <img
      className="delivery-image"
      src={`/api/datasets/${encodeURIComponent(datasetId)}/files/${encodeURIComponent(file.id)}/download?version=${encodeURIComponent(versionId)}`}
      alt={file.filename}
      loading="lazy"
      onError={() => {
        setFailed(true);
      }}
    />
  );
}

export function DeliveryLeakage({
  report,
  split,
  version,
  excluded,
  onExclude,
}: {
  report: LeakageReport;
  split: SplitSet;
  version: Version;
  excluded: ReadonlySet<string>;
  onExclude: (id: string, checked: boolean) => void;
}) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(pageSize);
  const files = new Map(version.manifest.map((file) => [file.id, file]));
  const members = new Map(
    split.members.map((member) => [member.sample_id, member]),
  );
  const pairs = groupPairs(report.pairs);
  return (
    <section aria-label={t("trainingLeakage")} className="delivery-leakage">
      <p className="muted">
        {t("deliverySeenPairs", { count: report.pairs.length })}
      </p>
      <ol className="delivery-pairs">
        {pairs.slice(0, visible).map((signals) => {
          const [pair] = signals;
          const sides = [
            { id: pair.left_id, split: pair.left_split },
            { id: pair.right_id, split: pair.right_split },
          ];
          return (
            <li
              className="delivery-pair"
              key={JSON.stringify(sides.map((side) => side.id))}
            >
              <div className="delivery-signals">
                {signals.map((signal) => (
                  <Badge tone="warn" key={signal.kind} title={signal.detail}>
                    {t(signalLabel[signal.kind])} · {t("distance")}{" "}
                    {signal.distance}
                  </Badge>
                ))}
              </div>
              <div className="delivery-sides">
                {sides.map((side) => {
                  const file = files.get(side.id);
                  const name = file?.filename ?? side.id;
                  const labels = members.get(side.id)?.labels ?? [];
                  return (
                    <article key={side.id} className="delivery-sample">
                      {file && (
                        <FilePreview
                          datasetId={split.dataset_id}
                          versionId={version.id}
                          file={file}
                        />
                      )}
                      <div className="delivery-sample-details">
                        <Badge>{t(splitLabel[side.split])}</Badge>
                        <strong>{name}</strong>
                        <p className="muted">
                          {labels.join(", ") || t("deliveryNoLabels")}
                        </p>
                        {file && (
                          <label className="delivery-checkbox">
                            <input
                              type="checkbox"
                              checked={excluded.has(side.id)}
                              aria-label={t("deliveryExcludeSample", { name })}
                              onChange={(event) => {
                                onExclude(side.id, event.target.checked);
                              }}
                            />
                            {t("deliveryExcludeSample", { name })}
                          </label>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            </li>
          );
        })}
      </ol>
      {visible < pairs.length && (
        <Button
          onClick={() => {
            setVisible((count) => count + pageSize);
          }}
        >
          {t("deliveryMorePairs")}
        </Button>
      )}
    </section>
  );
}
