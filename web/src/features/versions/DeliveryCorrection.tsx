import { useState } from "react";

import { post } from "../../api/client";
import { lineageHref } from "../../app/lineageNavigation";
import { Button } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";
import { PlanCard } from "../actions/PlanCard";

import type { components } from "../../api/generated";
import type { ActionPlan, ActionRun, Version } from "../../api/types";

const selectionLimit = 10000;

export function DeliveryCorrection({
  datasetId,
  version,
  excluded,
  onCorrected,
}: {
  datasetId: string;
  version: Version;
  excluded: ReadonlySet<string>;
  onCorrected: (id: string) => void;
}) {
  const { t } = useI18n();
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const keep = new Set(
    version.manifest
      .filter((file) => !excluded.has(file.id))
      .map((file) => file.id),
  );
  const selectable =
    keep.size > 0 &&
    keep.size <= selectionLimit &&
    keep.size + excluded.size === version.file_count;
  async function prepare() {
    if (busy || !selectable) return;
    setBusy(true);
    setError("");
    try {
      const selection: components["schemas"]["ObjectSet"] = {
        schema_version: "1.1",
        object_type: "file",
        namespace: "default",
        include_deleted: false,
        dataset_id: datasetId,
        version_ids: [version.id],
        filters: [{ field: "id", operator: "in", value: [...keep] }],
        limit: keep.size,
      };
      const next = await post<ActionPlan>(
        "/api/actions/create_version_from_selection/prepare",
        { selection },
      );
      const refs = next.manifest.objects.map((item) => item.asset_ref);
      if (
        next.manifest.truncated ||
        new Set(refs.map((item) => item.asset_id)).size !== keep.size ||
        refs.some(
          (item) => item.version !== version.id || !keep.has(item.asset_id),
        )
      ) {
        setError(t("deliverySelectionChanged"));
        return;
      }
      setPlan(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  function resolve(run: ActionRun | null) {
    const output = run?.receipt?.outputs?.find(
      (item) => item.asset_type === "version",
    );
    if (run?.status === "SUCCEEDED" && output) onCorrected(output.asset_id);
    if (!run) setPlan(null);
  }
  return (
    <div className="delivery-correction">
      <div className="delivery-review-bar">
        <div>
          <strong role="status">
            {t("deliveryExcludeCount", { count: excluded.size })}
          </strong>
          <p className="muted">
            {t(
              selectable
                ? "deliveryCorrectionHint"
                : "deliverySelectionUnavailable",
            )}
          </p>
        </div>
        {!plan && (
          <Button
            variant="primary"
            disabled={busy || !selectable}
            onClick={() => void prepare()}
          >
            {t("deliveryCorrection")}
          </Button>
        )}
      </div>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {plan && (
        <PlanCard
          plan={plan}
          onResolved={resolve}
          onInvalidated={() => {
            setPlan(null);
          }}
          onOpenReceipt={(target) => {
            window.location.hash = lineageHref(target);
          }}
        />
      )}
    </div>
  );
}
