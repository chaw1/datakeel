import { useI18n } from "../../i18n/useI18n";
import { PlanCard } from "../actions/PlanCard";

import type { useAssetAction } from "./useAssetAction";
import type { LineageTarget } from "../../app/navigation";

export function AssetPlanFeedback({
  action,
  onChanged,
  onOpenReceipt,
}: {
  action: ReturnType<typeof useAssetAction>;
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  return (
    <>
      {action.error && (
        <p className="error-text" role="alert">
          {action.error}
        </p>
      )}
      {action.saved && <p role="status">{t("assetChanged")}</p>}
      {action.plan && (
        <PlanCard
          plan={action.plan}
          onResolved={action.resolved}
          onInvalidated={onChanged}
          onOpenReceipt={onOpenReceipt}
        />
      )}
    </>
  );
}
