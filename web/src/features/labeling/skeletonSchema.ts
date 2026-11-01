import type { SkeletonDefinition } from "./editors/types";

export function defaultSkeleton(): SkeletonDefinition {
  return {
    points: [
      {
        id: "point-1",
        name: "Point 1",
        name_zh: "点 1",
        name_en: "Point 1",
        required: true,
      },
    ],
    edges: [],
  };
}

export function skeletonProblem(schema: SkeletonDefinition): boolean {
  const ids = schema.points.map((point) => point.id.trim());
  const names = schema.points.map((point) => point.name.trim());
  const edges = schema.edges.map(([left, right]) =>
    [left, right].sort().join("\u0000"),
  );
  return (
    !schema.points.length ||
    ids.some((id) => !id) ||
    names.some((name) => !name) ||
    new Set(ids).size !== ids.length ||
    new Set(edges).size !== edges.length ||
    schema.edges.some(
      ([left, right]) =>
        left === right || !ids.includes(left) || !ids.includes(right),
    )
  );
}

export function nextPointId(schema: SkeletonDefinition): string {
  let index = schema.points.length + 1;
  while (schema.points.some((point) => point.id === `point-${String(index)}`))
    index += 1;
  return `point-${String(index)}`;
}
