import { useState } from "react";

import { scopeLabels } from "../../api/dataAssets";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { useResource } from "../../lib/useResource";

import type { AssetUsage } from "../../api/dataAssets";

export function AssetAudit({ assetId }: { assetId?: string }) {
  const { t, locale } = useI18n();
  const isComposing = useCompositionGuard();
  const [actor, setActor] = useState("");
  const [query, setQuery] = useState("");
  const params = new URLSearchParams({
    limit: "100",
  });
  if (assetId) params.set("asset_id", assetId);
  if (query) params.set("actor", query);
  const audit = useResource<AssetUsage[]>(
    `/api/data-assets/audit?${params.toString()}`,
  );
  return (
    <section className="asset-section">
      <h2>{t("assetAudit")}</h2>
      <p className="muted">{t("assetAuditIntro")}</p>
      <form
        className="asset-controls"
        onKeyDownCapture={(event) => {
          if (event.key === "Enter" && isComposing(event.nativeEvent))
            event.preventDefault();
        }}
        onSubmit={(event) => {
          event.preventDefault();
          if (!isComposing()) {
            setQuery(actor.trim());
            audit.reload();
          }
        }}
      >
        <label>
          {t("assetAuditActor")}
          <input
            value={actor}
            onChange={(event) => {
              setActor(event.target.value);
            }}
          />
        </label>
        <button className="button" type="submit">
          {t("assetAuditSearch")}
        </button>
      </form>
      <ResourceState {...audit} onRetry={audit.reload} />
      {audit.value?.length === 0 && (
        <p className="muted">{t("assetAuditEmpty")}</p>
      )}
      {(audit.value?.length ?? 0) > 0 && (
        <div className="asset-table-scroll">
          <table>
            <thead>
              <tr>
                {(
                  [
                    "assetAuditTime",
                    "assetActor",
                    "assetAuditAsset",
                    "assetAuditEntry",
                    "assetAuditScope",
                    "assetAuditGrant",
                  ] as const
                ).map((key) => (
                  <th key={key}>{t(key)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {audit.value?.map((item) => (
                <tr key={item.id}>
                  <td>{date(item.occurred_at, locale)}</td>
                  <td>{item.actor}</td>
                  <td className="mono">{item.asset_id}</td>
                  <td>{item.entry}</td>
                  <td>{t(scopeLabels[item.scope])}</td>
                  <td className="mono">{item.grant_id ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
