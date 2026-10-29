import type { ProductionLabel, ProductionTemplate } from "./types";

export function labelShortcut(
  label: ProductionLabel,
  index: number,
  template: ProductionTemplate,
): string {
  const configured = template.component_config?.shortcuts;
  const override: unknown =
    configured && typeof configured === "object" && !Array.isArray(configured)
      ? Object.entries(configured).find(([id]) => id === label.id)?.[1]
      : null;
  return typeof override === "string"
    ? override
    : (label.shortcut ?? (index < 9 ? String(index + 1) : ""));
}
export function shortcutLabel(
  event: KeyboardEvent,
  labels: readonly ProductionLabel[],
  template: ProductionTemplate,
): ProductionLabel | undefined {
  if (event.ctrlKey || event.metaKey || event.altKey || event.isComposing)
    return undefined;
  return labels.find(
    (label, index) =>
      labelShortcut(label, index, template).toLowerCase() ===
      event.key.toLowerCase(),
  );
}
