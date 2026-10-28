import { useI18n } from "../../i18n/useI18n";

import { AssetPlanFeedback } from "./AssetPlanFeedback";
import { useAssetAction } from "./useAssetAction";

import type { DataAsset } from "../../api/dataAssets";
import type { LineageTarget } from "../../app/navigation";

export function AssetPublication({
  asset,
  onChanged,
  onOpenReceipt,
}: {
  asset: DataAsset;
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const action = useAssetAction(onChanged);
  const publish = asset.status !== "published";
  return (
    <section className="asset-section">
      <p className="muted">{t("assetControlled")}</p>
      <button
        className="button"
        disabled={action.busy}
        onKeyDown={(event) => {
          if (action.isComposing(event.nativeEvent)) event.preventDefault();
        }}
        onClick={() => {
          void action.prepare(
            publish ? "publish_data_asset" : "withdraw_data_asset",
            { asset_id: asset.id },
          );
        }}
      >
        {t(
          action.busy
            ? "assetPreparing"
            : publish
              ? "assetPublish"
              : "assetWithdraw",
        )}
      </button>
      <AssetPlanFeedback
        action={action}
        onChanged={onChanged}
        onOpenReceipt={onOpenReceipt}
      />
    </section>
  );
}
