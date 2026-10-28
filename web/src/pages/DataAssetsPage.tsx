import { useState } from "react";

import { classifications } from "../api/dataAssets";
import { Icon } from "../components/Icon";
import { ResourceState } from "../components/ResourceState";
import { AssetAudit } from "../features/data-assets/AssetAudit";
import { AssetDetail } from "../features/data-assets/AssetDetail";
import { AssetEditor } from "../features/data-assets/AssetEditor";
import { AssetSummary } from "../features/data-assets/AssetSummary";
import { useI18n } from "../i18n/useI18n";
import { useCompositionGuard } from "../lib/useCompositionGuard";
import { useResource } from "../lib/useResource";

import type { AssetMarketPage } from "../api/dataAssets";
import type { LineageTarget } from "../app/navigation";

import "../features/data-assets/data-assets.css";

const sorts = [
  ["popular", "assetPopular"],
  ["freshness", "assetFreshness"],
  ["quality", "assetQuality"],
  ["downstream", "assetDownstream"],
  ["name", "assetNameSort"],
] as const;

export function DataAssetsPage({
  onDataChanged,
  onOpenReceipt,
}: {
  onDataChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const initial = new URLSearchParams(window.location.hash.split("?")[1]);
  const selected = initial.get("asset");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [classification, setClassification] = useState("");
  const [tag, setTag] = useState("");
  const [sort, setSort] = useState("popular");
  const [manage, setManage] = useState(false);
  const [creating, setCreating] = useState(false);
  const [audit, setAudit] = useState(initial.get("view") === "audit");
  const params = new URLSearchParams({
    search: query,
    sort,
    limit: "100",
    include_unpublished: String(manage),
  });
  if (classification) params.set("classification", classification);
  if (tag.trim()) params.set("tag", tag.trim());
  const market = useResource<AssetMarketPage>(
    selected || audit ? null : `/api/data-assets?${params.toString()}`,
  );
  function changed() {
    market.reload();
    onDataChanged();
  }
  if (selected)
    return (
      <div className="data-assets-page">
        <AssetDetail
          assetId={selected}
          onChanged={changed}
          onOpenReceipt={onOpenReceipt}
        />
      </div>
    );
  return (
    <div className="data-assets-page">
      <div className="page-heading">
        <div>
          <h1>
            {t("assetMarket")} · {market.value?.total ?? 0}
          </h1>
          <p>{t("assetMarketIntro")}</p>
        </div>
        <button
          className="button primary"
          aria-label={t(creating ? "assetCancelEdit" : "assetNew")}
          title={t(creating ? "assetCancelEdit" : "assetNew")}
          onClick={() => {
            setCreating(!creating);
            setAudit(false);
          }}
        >
          <Icon name={creating ? "close" : "file"} />
          {t(creating ? "assetCancelEdit" : "assetNew")}
        </button>
      </div>
      <nav className="tabs" aria-label={t("assetMarket")}>
        <button
          className={audit ? "" : "active"}
          aria-current={!audit ? "page" : undefined}
          onClick={() => {
            setAudit(false);
          }}
        >
          {t("assetMarket")}
        </button>
        <button
          className={audit ? "active" : ""}
          aria-current={audit ? "page" : undefined}
          onClick={() => {
            setAudit(true);
            setCreating(false);
          }}
        >
          {t("assetAuditAll")}
        </button>
      </nav>
      {creating && (
        <AssetEditor onChanged={changed} onOpenReceipt={onOpenReceipt} />
      )}
      {audit ? (
        <AssetAudit />
      ) : (
        <>
          <form
            className="card asset-market-filters"
            onKeyDownCapture={(event) => {
              if (event.key === "Enter" && isComposing(event.nativeEvent))
                event.preventDefault();
            }}
            onSubmit={(event) => {
              event.preventDefault();
              if (!isComposing()) setQuery(search.trim());
            }}
          >
            <label className="asset-search">
              {t("assetSearch")}
              <input
                type="search"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                }}
              />
            </label>
            <label>
              {t("assetClassification")}
              <select
                value={classification}
                onBlur={(event) => {
                  setClassification(event.target.value);
                }}
                onChange={(event) => {
                  setClassification(event.target.value);
                }}
              >
                <option value="">{t("assetAllClasses")}</option>
                {classifications.map(([value, label]) => (
                  <option key={value} value={value}>
                    {t(label)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("assetTag")}
              <input
                value={tag}
                onChange={(event) => {
                  setTag(event.target.value);
                }}
              />
            </label>
            <label>
              {t("assetSort")}
              <select
                value={sort}
                onBlur={(event) => {
                  setSort(event.target.value);
                }}
                onChange={(event) => {
                  setSort(event.target.value);
                }}
              >
                {sorts.map(([value, label]) => (
                  <option key={value} value={value}>
                    {t(label)}
                  </option>
                ))}
              </select>
            </label>
            <button className="button" type="submit">
              {t("assetSearchSubmit")}
            </button>
            <label className="asset-manage">
              <input
                type="checkbox"
                checked={manage}
                onChange={(event) => {
                  setManage(event.target.checked);
                }}
              />
              {t("assetManage")}
            </label>
          </form>
          <p className="muted asset-sort-rule">{t("assetSortRule")}</p>
          <ResourceState {...market} onRetry={market.reload} />
          {market.value?.items.length === 0 && (
            <div className="card empty-state">{t("assetEmpty")}</div>
          )}
          <div className="asset-market-grid">
            {market.value?.items.map((card) => (
              <a
                key={card.asset.id}
                className="card asset-market-card"
                href={`#/data-assets?${new URLSearchParams({ asset: card.asset.id }).toString()}`}
              >
                <AssetSummary card={card} />
              </a>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
