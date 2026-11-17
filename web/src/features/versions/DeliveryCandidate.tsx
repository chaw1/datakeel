import { useState } from "react";

import { createSplit, trainingPath } from "../../api/training";
import { ResourceState } from "../../components/ResourceState";
import { Badge, Button } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";
import { objectHref } from "../object/navigation";
import { PublishRelease } from "../releases/PublishRelease";
import { ReleaseDetail } from "../releases/ReleaseDetail";

import { DeliveryCorrection } from "./DeliveryCorrection";
import { DeliveryLeakage } from "./DeliveryLeakage";
import { DeliveryVersionChanges } from "./DeliveryVersionChanges";

import type { LeakageReport, SplitRequest, SplitSet } from "../../api/training";
import type { Version } from "../../api/types";

const reviewRequest = {
  name: "Delivery review",
  source: "directory",
  avoid_leakage: true,
  image_threshold: 8,
  text_threshold: 3,
  seed: 42,
  stratify: true,
  stratification_source: "all",
} satisfies SplitRequest;
const partitionLabel = {
  train: "trainingTrain",
  val: "trainingVal",
  test: "trainingTest",
} as const;

function labelCounts(split: SplitSet) {
  const totals = new Map<string, number>();
  for (const partition of split.distributions)
    for (const { label, count } of partition.labels)
      totals.set(label, (totals.get(label) ?? 0) + count);
  return [...totals].sort(
    ([left, a], [right, b]) => b - a || left.localeCompare(right),
  );
}

function missingAnnotations(version: Version) {
  return version.manifest.filter((file) => {
    const paired = file.metadata?.evidence_sample;
    return (
      paired &&
      typeof paired === "object" &&
      !Array.isArray(paired) &&
      (!("annotation" in paired) || paired.annotation === null)
    );
  }).length;
}

export function DeliveryCandidate({
  datasetId,
  version,
  baseline,
  corrected,
  onCorrected,
  onChanged,
}: {
  datasetId: string;
  version: Version;
  baseline?: Version;
  corrected: boolean;
  onCorrected: (id: string) => void;
  onChanged?: () => void;
}) {
  const { t } = useI18n();
  const [createdSplit, setCreatedSplit] = useState<SplitSet | null>(null);
  const [excluded, setExcluded] = useState<ReadonlySet<string>>(new Set());
  const [release, setRelease] = useState<{ id: string; runId: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const path = trainingPath(datasetId, version.id);
  const splits = useResource<SplitSet[]>(`${path}/splits`);
  const split =
    createdSplit ??
    splits.value?.find(
      (item) =>
        item.request.name === reviewRequest.name &&
        item.request.source === reviewRequest.source,
    );
  const report = useResource<LeakageReport>(
    split ? `${path}/splits/${encodeURIComponent(split.id)}/leakage` : null,
  );
  const checked = report.loading ? null : report.value;
  const blocked = !!checked?.pairs.length;
  const incomplete =
    (split?.distributions.filter((partition) => partition.count > 0).length ??
      0) < 2;
  const uncheckedCount = split ? version.file_count - split.members.length : 0;
  const ready = !!checked && !blocked && !incomplete && uncheckedCount === 0;
  const labels = split ? labelCounts(split) : [];
  const missing = missingAnnotations(version);
  async function check() {
    if (busy || report.loading) return;
    setExcluded(new Set());
    setError("");
    if (split) {
      report.reload();
      return;
    }
    setBusy(true);
    try {
      setCreatedSplit(
        await createSplit(datasetId, version.id, reviewRequest, false),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  function exclude(id: string, checked: boolean) {
    setExcluded((previous) => {
      const next = new Set(previous);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }
  return (
    <div className="delivery-candidate">
      <DeliveryVersionChanges
        datasetId={datasetId}
        version={version}
        baseline={baseline}
      />
      {corrected && !checked && <p role="status">{t("deliveryCorrected")}</p>}
      <div className="delivery-review-bar">
        <div>
          <Badge
            tone={blocked ? "danger" : ready ? "ok" : "neutral"}
            dot
            role="status"
            data-delivery-status={
              blocked ? "blocked" : ready ? "ready" : "pending"
            }
          >
            {t(
              blocked
                ? "deliveryBlocked"
                : ready
                  ? "deliveryReady"
                  : checked
                    ? uncheckedCount !== 0
                      ? "deliveryUnassigned"
                      : "deliveryIncomplete"
                    : "deliveryUnchecked",
            )}
          </Badge>
          {split && (
            <div
              className="delivery-partitions"
              role="group"
              aria-label={t("trainingDistribution")}
            >
              {split.distributions.map((partition) => (
                <span key={partition.split}>
                  {t(partitionLabel[partition.split])}{" "}
                  <strong>{partition.count}</strong>
                </span>
              ))}
            </div>
          )}
          {uncheckedCount > 0 && (
            <p className="muted">
              {t("deliveryUnknownSplits", { count: uncheckedCount })}
            </p>
          )}
        </div>
        <Button
          variant={split ? "secondary" : "primary"}
          icon="refresh"
          disabled={busy || report.loading || splits.loading}
          onClick={() => void check()}
        >
          {t(split ? "deliveryRecheck" : "deliveryCheck")}
        </Button>
      </div>
      <ResourceState
        loading={splits.loading || report.loading || busy}
        error={error || splits.error || report.error}
        onRetry={
          error
            ? () => void check()
            : splits.error
              ? splits.reload
              : report.reload
        }
      />
      {(labels.length > 0 || missing > 0) && (
        <div className="delivery-datasheet">
          {labels.length > 0 && (
            <details className="delivery-labels">
              <summary>
                {t("deliveryLabelCounts", { count: labels.length })}
              </summary>
              <ul>
                {labels.map(([label, count]) => (
                  <li key={label}>
                    {label} <strong>{count}</strong>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {missing > 0 && (
            <Badge tone="warn">
              {t("deliveryMissingAnnotations", { count: missing })}
            </Badge>
          )}
        </div>
      )}
      {split && checked && blocked && (
        <DeliveryLeakage
          report={checked}
          split={split}
          version={version}
          excluded={excluded}
          onExclude={exclude}
        />
      )}
      {blocked && excluded.size > 0 && (
        <DeliveryCorrection
          key={JSON.stringify([...excluded].sort())}
          datasetId={datasetId}
          version={version}
          excluded={excluded}
          onCorrected={onCorrected}
        />
      )}
      {split && ready && !release && (
        <PublishRelease
          key={`${split.id}:${baseline?.id ?? ""}`}
          versions={[version]}
          datasetId={datasetId}
          review={{
            split_id: split.id,
            ...(baseline ? { baseline_version_id: baseline.id } : {}),
          }}
          onChanged={() => {
            onChanged?.();
          }}
          onPublished={(id, runId) => {
            setRelease({ id, runId });
          }}
        />
      )}
      {release && (
        <div>
          <a
            className="text-button"
            href={objectHref({ kind: "action_run", id: release.runId })}
          >
            {t("deliveryReceipt")}
          </a>
          <ReleaseDetail releaseId={release.id} />
        </div>
      )}
    </div>
  );
}
