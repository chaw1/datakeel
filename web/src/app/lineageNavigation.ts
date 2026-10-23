import type { LineageTarget } from "./navigation";
export function lineageHref(target: LineageTarget): string {
  const params = new URLSearchParams({
    [target.includeSemantic || target.includeCatalog ? "asset_id" : "asset"]:
      target.assetId ?? "",
    event: target.eventId ?? "",
    dataset: target.datasetId ?? "",
  });
  if (target.includeCatalog) params.set("include_catalog", "true");
  return `#lineage?${params.toString()}`;
}
export function readLineageTarget(hash: string): LineageTarget | undefined {
  if (!hash.startsWith("#lineage?")) return undefined;
  const params = new URLSearchParams(hash.slice("#lineage?".length));
  return {
    datasetId: params.get("dataset") ?? undefined,
    eventId: params.get("event") ?? undefined,
    assetId: params.get("asset_id") ?? params.get("asset") ?? undefined,
    ...(params.get("include_catalog") === "true"
      ? { includeCatalog: true }
      : params.has("asset_id")
        ? { includeSemantic: true }
        : {}),
  };
}
