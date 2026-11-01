import type {
  AnnotationKeypoint,
  AnnotationRecord,
  AnnotationSkeleton,
  Attributes,
  ProductionTemplate,
  SkeletonDefinition,
} from "./types";
import type { Translate } from "../../../i18n/context";

export function templateSkeleton(
  template: ProductionTemplate,
): SkeletonDefinition | null {
  return template.keypoint_schema ?? null;
}

export function normalizeSkeleton(
  skeleton: AnnotationSkeleton,
  schema: SkeletonDefinition,
): AnnotationSkeleton {
  const byId = new Map(skeleton.points.map((point) => [point.id, point]));
  return {
    ...skeleton,
    points: schema.points.map(
      (definition) =>
        byId.get(definition.id) ?? { id: definition.id, state: "missing" },
    ),
  };
}

export function blankSkeleton(
  category: string,
  schema: SkeletonDefinition,
  attributes: Attributes,
): AnnotationSkeleton {
  return normalizeSkeleton({ category, points: [], attributes }, schema);
}

export function firstMissing(skeleton: AnnotationSkeleton | undefined): number {
  return Math.max(
    0,
    skeleton?.points.findIndex((point) => point.state === "missing") ?? 0,
  );
}

export function positioned(
  point: AnnotationKeypoint,
): point is AnnotationKeypoint & {
  x: number;
  y: number;
} {
  return point.state !== "missing" && point.x != null && point.y != null;
}

export function keypointSubmissionProblem(
  annotation: AnnotationRecord,
  template: ProductionTemplate,
  t: Translate,
): string {
  const schema = templateSkeleton(template);
  const configured = template.component_config?.components;
  const enabled = Array.isArray(configured)
    ? configured.includes("keypoints")
    : template.annotation_type === "keypoints";
  if (!schema) return enabled ? t("wbKeypointSchemaMissing") : "";
  const definitions = new Map(schema.points.map((point) => [point.id, point]));
  for (const [index, skeleton] of (annotation.keypoints ?? []).entries()) {
    const points = new Map(skeleton.points.map((point) => [point.id, point]));
    if (!skeleton.points.some((point) => point.state !== "missing"))
      return t("wbKeypointAllMissing", { index: index + 1 });
    const required = schema.points.filter(
      (definition) =>
        definition.required &&
        (points.get(definition.id)?.state ?? "missing") === "missing",
    );
    if (required.length)
      return t("wbKeypointRequiredMissing", {
        index: index + 1,
        points: required.map((point) => point.name).join(", "),
      });
    if (skeleton.points.some((point) => !definitions.has(point.id)))
      return t("wbKeypointUnknown", { index: index + 1 });
  }
  return "";
}
