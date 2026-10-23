import { impactPath } from "../../api/catalog";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import { impactBranches } from "./values";

import type { ImpactBranch } from "./values";
import type { ImpactResult } from "../../api/catalog";
import type { LineageTarget } from "../../app/navigation";

export function ImpactTree({
  assetId,
  onOpenReceipt,
}: {
  assetId: string;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const resource = useResource<ImpactResult>(impactPath(assetId));
  const branches = resource.value ? impactBranches(resource.value) : [];
  function nodes(items: ImpactBranch[]) {
    return (
      <ul>
        {items.map(({ item, children }) => (
          <li key={item.asset_ref.asset_id}>
            <button
              className="text-button"
              onClick={() => {
                onOpenReceipt({
                  assetId: item.asset_ref.asset_id,
                  includeCatalog: true,
                });
              }}
            >
              {item.name}
            </button>
            <small className="mono">{item.asset_ref.asset_id}</small>
            {!!children.length && nodes(children)}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <section className="catalog-impact" aria-label={t("catImpact")}>
      <h3>{t("catImpact")}</h3>
      <p className="muted small">{t("catImpactScope")}</p>
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {resource.value && !resource.loading && !resource.error && (
        <>
          {nodes(branches)}
          {!branches.length && <p className="muted">{t("catImpactEmpty")}</p>}
          {resource.value.truncated && (
            <p role="status">{t("catImpactTruncated")}</p>
          )}
        </>
      )}
    </section>
  );
}
