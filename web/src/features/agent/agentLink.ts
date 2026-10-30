import type { PageContext } from "../../api/intents";

type Field = Exclude<keyof PageContext, "selected_ids" | "selected_kind">;

// URL names stay short and readable; "dataset" is the one older links already use.
const names: Record<Field, string> = {
  dataset_id: "dataset",
  version_id: "version",
  project_id: "project",
  package_id: "package",
  task_id: "task",
  label_set_id: "label_set",
};
const kinds: NonNullable<PageContext["selected_kind"]>[] = [
  "file",
  "production_task",
  "task_package",
];

/** Open the one-sentence entry carrying everything the current page shows. */
export function agentHref(context: Partial<PageContext>, prompt = ""): string {
  const query = new URLSearchParams();
  if (prompt) query.set("prompt", prompt);
  for (const [field, name] of Object.entries(names) as [Field, string][]) {
    const value = context[field];
    if (value) query.set(name, value);
  }
  if (context.selected_kind && context.selected_ids?.length) {
    query.set("selected_kind", context.selected_kind);
    query.set("selected", context.selected_ids.join(","));
  }
  return `#/agent?${query.toString()}`;
}

/** Read the page context an entry link carried; unknown values are ignored. */
export function contextFromQuery(query: URLSearchParams): PageContext {
  const context: PageContext = { selected_ids: [] };
  for (const [field, name] of Object.entries(names) as [Field, string][]) {
    const value = query.get(name);
    if (value) context[field] = value;
  }
  const kind = query.get("selected_kind");
  const selected = (query.get("selected") ?? "").split(",").filter(Boolean);
  const known = kinds.find((item) => item === kind);
  if (known && selected.length) {
    context.selected_kind = known;
    context.selected_ids = selected;
  }
  return context;
}
