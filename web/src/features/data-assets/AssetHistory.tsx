import { assetPath } from "../../api/dataAssets";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useResource } from "../../lib/useResource";

import type { AssetHistory as History } from "../../api/dataAssets";

export function AssetHistory({ assetId }: { assetId: string }) {
  const { t, locale } = useI18n();
  const history = useResource<History[]>(`${assetPath(assetId)}/history`);
  return (
    <section className="asset-section">
      <h2>{t("assetHistory")}</h2>
      <ResourceState {...history} onRetry={history.reload} />
      {history.value?.length === 0 && (
        <p className="muted">{t("assetNoHistory")}</p>
      )}
      {history.value?.map((item) => (
        <details className="asset-request" key={item.id}>
          <summary>
            {date(item.occurred_at, locale)} · {item.action} · {item.actor} ·{" "}
            {t("assetRevision")} {item.asset.revision}
          </summary>
          <pre>{JSON.stringify(item.asset.definition, null, 2)}</pre>
        </details>
      ))}
    </section>
  );
}
