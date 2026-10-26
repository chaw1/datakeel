import { useState } from "react";

import { assetPath } from "../../api/dataAssets";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";
import { objectHref, isObjectKind } from "../object/navigation";

import { AssetAccessForm } from "./AssetAccessForm";
import { AssetAccessHistory } from "./AssetAccessHistory";
import { AssetAudit } from "./AssetAudit";
import { AssetEditor } from "./AssetEditor";
import { AssetHistory } from "./AssetHistory";
import { AssetPublication } from "./AssetPublication";
import { AssetSummary } from "./AssetSummary";

import type { DataAssetCard } from "../../api/dataAssets";
import type { LineageTarget } from "../../app/navigation";

export function AssetDetail({
  assetId,
  onChanged,
  onOpenReceipt,
}: {
  assetId: string;
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const card = useResource<DataAssetCard>(assetPath(assetId));
  const [editing, setEditing] = useState(false);
  const [revision, setRevision] = useState(0);
  function changed() {
    setRevision((value) => value + 1);
    card.reload();
    onChanged();
  }
  const asset = card.value?.asset;
  const target = asset?.definition.target;
  return (
    <>
      <a className="text-button" href="#/data-assets">
        {t("assetBack")}
      </a>
      <ResourceState {...card} onRetry={card.reload} />
      {card.value && asset && (
        <>
          <div className="card asset-detail">
            <AssetSummary card={card.value} expanded />
          </div>
          <div className="asset-controls">
            <button
              className="button"
              onClick={() => {
                setEditing(!editing);
              }}
            >
              {t(editing ? "assetCancelEdit" : "assetEdit")}
            </button>
            {target && isObjectKind(target.asset_type) && (
              <a
                className="button"
                href={objectHref({
                  kind: target.asset_type,
                  id: target.asset_id,
                  versionId: target.version ?? undefined,
                  tab: "facts",
                })}
              >
                {t("assetOpenTarget")}
              </a>
            )}
            <a className="button" href="#/ask">
              {t("assetAsk")}
            </a>
          </div>
          <AssetPublication
            asset={asset}
            onChanged={changed}
            onOpenReceipt={onOpenReceipt}
          />
          {editing && (
            <AssetEditor
              key={asset.revision}
              asset={asset}
              onChanged={changed}
              onOpenReceipt={onOpenReceipt}
            />
          )}
          {asset.status === "published" && (
            <AssetAccessForm assetId={asset.id} onChanged={changed} />
          )}
          <AssetAccessHistory
            assetId={asset.id}
            key={`access:${String(revision)}`}
            onChanged={changed}
            onOpenReceipt={onOpenReceipt}
          />
          <AssetAudit key={`audit:${String(revision)}`} assetId={asset.id} />
          <AssetHistory
            key={`history:${String(revision)}`}
            assetId={asset.id}
          />
        </>
      )}
    </>
  );
}
