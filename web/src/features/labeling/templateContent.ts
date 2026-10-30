import type {
  AnnotationRecord,
  ProductionTemplate,
} from "../../api/production";
import type { Translate } from "../../i18n/context";

type ContentKey = "boxes" | "polygons" | "labels" | "spans";

/** Where each editor component keeps its objects in the annotation record. */
const contentKeys: Partial<Record<string, ContentKey>> = {
  box: "boxes",
  bbox: "boxes",
  polygon: "polygons",
  classification: "labels",
  text_span: "spans",
  span: "spans",
};

/** The editor components a template enables, in display order. */
export function templateComponents(template: ProductionTemplate): string[] {
  const configured = template.component_config?.components;
  return [
    ...new Set(
      Array.isArray(configured) && configured.length
        ? configured.filter((item): item is string => typeof item === "string")
        : [template.annotation_type],
    ),
  ];
}

function enabledKeys(template: ProductionTemplate): ContentKey[] {
  return [
    ...new Set(
      templateComponents(template).flatMap((component) => {
        const key = contentKeys[component];
        return key ? [key] : [];
      }),
    ),
  ];
}

/** An empty list for every enabled component: the server rejects a record with none of them. */
export function emptyContent(
  template: ProductionTemplate,
): Pick<AnnotationRecord, ContentKey> {
  return Object.fromEntries(enabledKeys(template).map((key) => [key, []]));
}

function bound(template: ProductionTemplate, rule: string) {
  const value = template.validation_rules?.[rule];
  return typeof value === "number" ? value : null;
}

/** The template's min/max annotation rule the server enforces on every save, or "". */
export function countProblem(
  annotation: AnnotationRecord,
  template: ProductionTemplate,
  t: Translate,
) {
  const count = enabledKeys(template).reduce(
    (total, key) => total + (annotation[key]?.length ?? 0),
    0,
  );
  const minimum = bound(template, "min_annotations");
  if (minimum != null && count < minimum)
    return t("wbTooFewAnnotations", { minimum, count });
  const maximum = bound(template, "max_annotations");
  if (maximum != null && count > maximum)
    return t("wbTooManyAnnotations", { maximum, count });
  return "";
}
