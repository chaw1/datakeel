import type { AnnotationRecord, Attributes, ProductionTemplate } from "./types";
import type { components } from "../../../api/generated";

export type AttributeField = components["schemas"]["TemplateAttribute"];
export type AttributeTarget = AttributeField["target"];

/** Where a problem was found: the record itself or the Nth shape of one kind (1-based). */
export interface AttributeProblem {
  field: AttributeField;
  kind: "required" | "invalid";
  shape: "record" | "box" | "polygon" | "span";
  index: number;
}

export function attributeFields(
  template: ProductionTemplate,
  target: AttributeTarget,
): AttributeField[] {
  return template.attributes.filter((field) => field.target === target);
}

export function fieldName(field: AttributeField, locale: string) {
  return locale === "zh" ? field.name_zh : field.name_en;
}

export function optionName(
  field: AttributeField,
  value: string,
  locale: string,
) {
  const option = field.options.find((item) => item.value === value);
  return option ? (locale === "zh" ? option.name_zh : option.name_en) : value;
}

/** Fill configured defaults for keys that are absent, keeping every other value. */
export function withDefaults(
  value: Attributes | undefined,
  fields: readonly AttributeField[],
): Attributes {
  const next: Attributes = { ...(value ?? {}) };
  for (const field of fields)
    if (next[field.key] == null && field.default != null)
      next[field.key] = structuredClone(field.default);
  return next;
}

function missing(field: AttributeField, value: unknown) {
  if (value == null) return true;
  if (field.type === "multi_enum") return Array.isArray(value) && !value.length;
  return field.type === "text" && typeof value === "string" && !value.trim();
}

/** The same value rules as the server's template validation. */
export function valueFits(field: AttributeField, value: unknown): boolean {
  const choices = new Set(field.options.map((option) => option.value));
  switch (field.type) {
    case "boolean":
      return typeof value === "boolean";
    case "enum":
      return typeof value === "string" && choices.has(value);
    case "multi_enum":
      return (
        Array.isArray(value) &&
        value.every((item) => typeof item === "string" && choices.has(item)) &&
        new Set(value).size === value.length
      );
    case "number":
      return (
        typeof value === "number" &&
        Number.isFinite(value) &&
        (field.minimum == null || value >= field.minimum) &&
        (field.maximum == null || value <= field.maximum)
      );
    default:
      return typeof value === "string" && value.length <= field.max_length;
  }
}

function check(
  fields: readonly AttributeField[],
  values: Attributes | undefined,
  shape: AttributeProblem["shape"],
  index: number,
): AttributeProblem[] {
  return fields.flatMap((field): AttributeProblem[] => {
    const value = values?.[field.key];
    if (missing(field, value))
      return field.required ? [{ field, kind: "required", shape, index }] : [];
    return value != null && !valueFits(field, value)
      ? [{ field, kind: "invalid", shape, index }]
      : [];
  });
}

/** List missing required and invalid attribute values, in display order. */
export function attributeProblems(
  annotation: AnnotationRecord,
  template: ProductionTemplate,
): AttributeProblem[] {
  const objects = attributeFields(template, "object");
  return [
    ...check(
      attributeFields(template, "record"),
      annotation.attributes,
      "record",
      0,
    ),
    ...(annotation.boxes ?? []).flatMap((box, index) =>
      check(objects, box.attributes, "box", index + 1),
    ),
    ...(annotation.polygons ?? []).flatMap((polygon, index) =>
      check(objects, polygon.attributes, "polygon", index + 1),
    ),
    ...(annotation.spans ?? []).flatMap((span, index) =>
      check(objects, span.attributes, "span", index + 1),
    ),
  ];
}
