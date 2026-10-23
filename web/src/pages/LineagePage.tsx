import { ResourceState } from "../components/ResourceState";
import Lineage from "../features/lineage/Lineage";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { DatasetData, Graph } from "../api/types";
import type { LineageTarget } from "../app/navigation";
export function LineagePage({
  data,
  focus,
}: {
  data: DatasetData;
  selectedId: string;
  focus?: LineageTarget;
}) {
  const { t } = useI18n();
  const path =
    focus?.includeCatalog && focus.assetId
      ? `/api/lineage/graph?asset_id=${encodeURIComponent(focus.assetId)}&include_catalog=true&hops=2&max_nodes=30`
      : focus?.includeSemantic && focus.assetId
        ? `/api/lineage/graph?asset_id=${encodeURIComponent(focus.assetId)}&include_semantic=true&hops=2&max_nodes=200`
        : null;
  const resource = useResource<Graph>(path, data.graph);
  return (
    <section className="card">
      <div className="card-heading">
        <div>
          <h2>
            {t(focus?.includeCatalog ? "catalogLineageTitle" : "dataLineage")}
          </h2>
          <p>
            {t(
              focus?.includeCatalog
                ? "catalogLineageDescription"
                : "followTheAssetsAndEventsBehindEveryTransformation",
            )}{" "}
          </p>
        </div>
        <span className="badge green">{t("appendOnlyHistory")}</span>
      </div>
      <ResourceState {...resource} onRetry={resource.reload} />
      {resource.value && (
        <Lineage
          key={focus?.eventId ?? focus?.assetId ?? "browse"}
          graph={resource.value}
          focus={focus}
        />
      )}
    </section>
  );
}
