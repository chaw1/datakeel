import { inputLabel } from "./labels";

import type {
  WorkflowDefinition,
  WorkflowInput,
  WorkflowStart,
} from "../../api/workflows";
import type { Translate } from "../../i18n/context";

export function inputDefaults(
  definition: WorkflowDefinition,
  datasetId: string,
) {
  return Object.fromEntries(
    Object.entries(definition.inputs).map(([name, field]) => [
      name,
      name === "dataset_id" && datasetId
        ? datasetId
        : field.default === null || field.default === undefined
          ? ""
          : ["object", "array"].includes(field.type)
            ? JSON.stringify(field.default, null, 2)
            : typeof field.default === "string"
              ? field.default
              : JSON.stringify(field.default),
    ]),
  );
}
function parseField(value: string, field: WorkflowInput): unknown {
  if (field.type === "string") return value;
  if (field.type === "boolean") return value === "true";
  if (["number", "integer"].includes(field.type)) return Number(value);
  return JSON.parse(value) as unknown;
}
function validField(value: unknown, field: WorkflowInput): boolean {
  if (field.type === "integer")
    return typeof value === "number" && Number.isInteger(value);
  if (field.type === "number")
    return typeof value === "number" && Number.isFinite(value);
  if (field.type === "array") return Array.isArray(value);
  if (field.type === "object")
    return value !== null && typeof value === "object" && !Array.isArray(value);
  return typeof value === field.type;
}
export function formInputs(
  definition: WorkflowDefinition,
  values: Record<string, string>,
  t: Translate,
): WorkflowStart["inputs"] {
  const result: WorkflowStart["inputs"] = {};
  for (const [name, field] of Object.entries(definition.inputs)) {
    const raw = values[name] ?? "";
    if (!raw && !field.required) continue;
    try {
      if (!raw && field.type !== "boolean") throw new Error("Missing value");
      const value = parseField(raw, field);
      if (!validField(value, field)) throw new Error("Incorrect type");
      result[name] = value;
    } catch {
      throw new Error(
        t("workflowFieldInvalid", {
          field: inputLabel(name, t),
          type: field.type,
        }),
      );
    }
  }
  return result;
}
