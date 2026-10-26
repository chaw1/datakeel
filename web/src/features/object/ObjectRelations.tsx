import { get } from "../../api/client";
import { objectGraphPath } from "../../api/objects";
import { localizedObjectName } from "../../i18n/graphCatalogNames";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";
import { RelationGraph } from "../graph/RelationGraph";

import { objectCatalogGraph, objectRelationEdges } from "./descriptors";
import { isObjectKind, objectHref } from "./navigation";

import type { ObjectTarget } from "./navigation";
import type { CatalogObject } from "../../api/catalog";
import type { ObjectData } from "../../api/objects";
import type { Graph, GraphNode } from "../../api/types";

export function ObjectRelations({
  data,
  target,
  onOpen,
}: {
  data: ObjectData;
  target: ObjectTarget;
  onOpen: (target: ObjectTarget) => void;
}) {
  const { t, locale } = useI18n();
  const relation = target.relation;
  const sourceId = relation === "source" ? data.catalog?.source_id : undefined;
  const source = useResource<CatalogObject>(
    sourceId ? `/api/catalog/objects/${encodeURIComponent(sourceId)}` : null,
  );
  const detailMode = relation === "source" || relation === "owner";
  function scopedGraph(input: Graph): Graph {
    if (!relation || detailMode) return input;
    const source = objectCatalogGraph(data) ?? input;
    const edges = objectRelationEdges(
      { ...data, graph: source },
      target,
      relation,
    );
    const visible = new Set(
      edges.flatMap((edge) => [edge.source, edge.target]),
    );
    const focus =
      target.kind === "version" ? (target.datasetId ?? target.id) : target.id;
    return {
      ...source,
      edges,
      nodes: source.nodes.filter(
        (node) =>
          visible.has(node.id) || node.id === focus || node.asset_id === focus,
      ),
    };
  }
  const graph = scopedGraph(data.graph);
  const edges = graph.edges;
  function navigate(node: GraphNode) {
    if (!isObjectKind(node.asset_type)) return;
    if (node.asset_type === "dataset" && node.version) {
      onOpen({
        kind: "version",
        id: node.version,
        datasetId: node.asset_id,
        tab: "relations",
      });
      return;
    }
    onOpen({
      kind: node.asset_type,
      id: node.asset_id,
      datasetId: data.dataset?.id,
      versionId: node.version ?? undefined,
      tab: "relations",
    });
  }
  return (
    <section aria-label={t("objRelations")}>
      {relation && (
        <div className="object-relation-filter">
          <span>{t("objRelationFilter", { kind: relation })}</span>
          <a
            href={objectHref({
              ...target,
              relation: undefined,
              section: undefined,
            })}
          >
            {t("objClearRelation")}
          </a>
        </div>
      )}
      {detailMode && (
        <section
          id={`object-section-${relation}`}
          className="object-source-detail"
        >
          <h2>{t(relation === "source" ? "objSource" : "objOwner")}</h2>
          <p>
            {relation === "source"
              ? source.value
                ? localizedObjectName(
                    "source",
                    source.value.name,
                    locale,
                    source.value.english_name,
                  )
                : (sourceId ?? t("objNoSource"))
              : data.metric
                ? localizedObjectName(
                    "owner",
                    data.metric.definition.owner,
                    locale,
                    data.metric.owner_english_name,
                  )
                : (data.table?.owners
                    .map((owner) =>
                      localizedObjectName(
                        "owner",
                        owner.name,
                        locale,
                        owner.english_name,
                      ),
                    )
                    .join(", ") ?? t("objNoSource"))}
          </p>
          {source.value && (
            <dl>
              <dt>{t("objRevision")}</dt>
              <dd>{source.value.revision}</dd>
              <dt>{t("objSourceRecord")}</dt>
              <dd>
                <code>{source.value.asset_ref.asset_id}</code>
              </dd>
            </dl>
          )}
        </section>
      )}
      {relation && !detailMode && !edges.length && (
        <p className="empty-state">{t("objNoRelations")}</p>
      )}
      <RelationGraph
        graph={graph}
        focus={{
          assetId: target.kind === "version" ? target.datasetId : target.id,
          datasetId: data.dataset?.id,
          eventId: target.eventId,
          includeCatalog: true,
          includeSemantic: true,
        }}
        onNavigate={navigate}
        loadExpansion={async () =>
          scopedGraph(await get<Graph>(objectGraphPath(target, true)))
        }
      />
    </section>
  );
}
