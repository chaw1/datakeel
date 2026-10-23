import type {
  CatalogObject,
  ImpactResult,
  MetricFilter,
} from "../../api/catalog";

export const kindLabels = {
  source: "catSourceType",
  table: "catTableType",
  column: "catColumnType",
  metric: "catMetricType",
  dimension: "catDimensionType",
  term: "catTermType",
  owner: "catOwnerType",
} as const;

export const linkLabels = {
  contains: "catContains",
  derived: "catDerived",
  measures: "catMeasures",
  sliced_by: "catSlicedBy",
  references: "catReferences",
  owned_by: "catOwnedBy",
  means: "catMeansLink",
} as const;

export function propertyText(item: CatalogObject, key: string): string {
  const value = item.properties?.[key];
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : "";
}

export function synonyms(item: CatalogObject): string[] {
  const value = item.properties?.synonyms;
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === "string")
    : [];
}

export function termTarget(item: CatalogObject): string {
  const target = item.properties?.means;
  if (
    target &&
    typeof target === "object" &&
    "id" in target &&
    typeof target.id === "string"
  )
    return target.id;
  return "";
}

export function filterValue(value: string): string | number | boolean | null {
  const trimmed = value.trim();
  if (trimmed === "null") return null;
  if (trimmed === "true" || trimmed === "false") return trimmed === "true";
  if (trimmed && Number.isFinite(Number(trimmed))) return Number(trimmed);
  return trimmed;
}

export function serializeFilterValue(value: MetricFilter["value"]): string {
  return Array.isArray(value)
    ? value.map((entry) => String(entry)).join(", ")
    : String(value);
}

export type ImpactBranch = { item: CatalogObject; children: ImpactBranch[] };
export function impactBranches(result: ImpactResult): ImpactBranch[] {
  const objects = new Map(
    result.objects.map((item) => [item.asset_ref.asset_id, item]),
  );
  const next = new Map<string, Set<string>>();
  for (const link of result.links) {
    const reverse = ["contains", "measures", "means"].includes(link.kind);
    const from = reverse ? link.target.asset_id : link.source.asset_id;
    const to = reverse ? link.source.asset_id : link.target.asset_id;
    const targets = next.get(from) ?? new Set<string>();
    targets.add(to);
    next.set(from, targets);
  }
  const seen = new Set([result.asset_id]);
  const roots: ImpactBranch[] = [];
  const queue = [{ id: result.asset_id, depth: 0, children: roots }];
  for (let index = 0; index < queue.length; index++) {
    const node = queue[index];
    if (node.depth === 3) continue;
    for (const target of [...(next.get(node.id) ?? [])].sort()) {
      const item = objects.get(target);
      if (!item || seen.has(target)) continue;
      seen.add(target);
      const children: ImpactBranch[] = [];
      node.children.push({ item, children });
      queue.push({ id: target, depth: node.depth + 1, children });
    }
  }
  return roots;
}
