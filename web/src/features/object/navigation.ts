export const objectKinds = [
  "dataset",
  "file",
  "version",
  "action_run",
  "table",
  "column",
  "metric",
  "term",
] as const;
export type ObjectKind = (typeof objectKinds)[number];
export const objectTabs = [
  "facts",
  "relations",
  "evidence",
  "history",
  "files",
  "versions",
  "quality",
  "report",
  "datasheets",
] as const;
export type ObjectTab = (typeof objectTabs)[number];
export type ObjectTarget = {
  kind: ObjectKind;
  id: string;
  datasetId?: string;
  versionId?: string;
  tab?: ObjectTab;
  eventId?: string;
  relation?: string;
  section?: string;
};
export function isObjectKind(value: string): value is ObjectKind {
  return objectKinds.some((kind) => kind === value);
}
export function objectHref(target: ObjectTarget): string {
  const query = new URLSearchParams({ tab: target.tab ?? "relations" });
  for (const [key, value] of [
    ["dataset", target.datasetId],
    ["version", target.versionId],
    ["event", target.eventId],
    ["relation", target.relation],
    ["section", target.section],
  ] as const)
    if (value) query.set(key, value);
  return `#/object/${target.kind}/${encodeURIComponent(target.id)}?${query.toString()}`;
}
export function readObjectTarget(hash: string): ObjectTarget | undefined {
  const legacy = hash.startsWith("#object?");
  const [path, search = ""] = hash.split("?");
  const query = new URLSearchParams(search);
  const match = /^#\/object\/([^/]+)\/(.+)$/.exec(path);
  const kind = legacy ? query.get("kind") : match?.[1];
  const raw = legacy ? query.get("id") : match?.[2];
  if (!kind || !raw || !isObjectKind(kind)) return undefined;
  let id: string;
  try {
    id = legacy ? raw : decodeURIComponent(raw);
  } catch {
    return undefined;
  }
  const tab = query.get("tab");
  return {
    kind,
    id,
    datasetId: query.get("dataset") ?? undefined,
    versionId: query.get("version") ?? undefined,
    tab: objectTabs.find((value) => value === tab) ?? "relations",
    eventId: query.get("event") ?? undefined,
    relation: query.get("relation") ?? undefined,
    section: query.get("section") ?? undefined,
  };
}
