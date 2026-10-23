import type { GraphEdge, GraphNode } from "../../api/types";

const catalogTypes = [
  "source",
  "table",
  "column",
  "metric",
  "dimension",
  "term",
  "owner",
];

function layoutCatalog(nodes: GraphNode[]) {
  const kinds = [...new Set(nodes.map((node) => node.asset_type))];
  const order = [
    ...catalogTypes.filter((kind) => kinds.includes(kind)),
    ...kinds.filter((kind) => !catalogTypes.includes(kind)).sort(),
  ];
  const positions = new Map<string, { x: number; y: number }>();
  let rows = 0;
  const columns = order.map((kind, column) => {
    const group = nodes
      .filter((node) => node.asset_type === kind)
      .sort((left, right) => {
        const a = left.asset_id;
        const b = right.asset_id;
        return a < b ? -1 : a > b ? 1 : 0;
      });
    group.forEach((node, row) =>
      positions.set(node.id, { x: 32 + column * 242, y: 60 + row * 106 }),
    );
    rows = Math.max(rows, group.length);
    return { kind, x: 32 + column * 242 };
  });
  return {
    positions,
    columns,
    width: Math.max(640, 58 + order.length * 242),
    height: Math.max(230, 110 + rows * 106),
  };
}

export function layoutGraph(nodes: GraphNode[], edges: GraphEdge[]) {
  if (nodes.some((node) => catalogTypes.includes(node.asset_type)))
    return layoutCatalog(nodes);
  const lineageEdges = edges.filter((edge) => edge.kind !== "semantic");
  const levels = new Map(nodes.map((node) => [node.id, 0]));
  const indegree = new Map(nodes.map((node) => [node.id, 0]));
  lineageEdges.forEach((edge) => {
    if (indegree.has(edge.target))
      indegree.set(edge.target, (indegree.get(edge.target) || 0) + 1);
  });
  const queue = nodes
    .filter((node) => !indegree.get(node.id))
    .map((node) => node.id);
  for (let i = 0; i < queue.length; i++) {
    const id = queue[i];
    lineageEdges
      .filter((edge) => edge.source === id)
      .forEach((edge) => {
        levels.set(
          edge.target,
          Math.max(levels.get(edge.target) || 0, (levels.get(id) || 0) + 1),
        );
        indegree.set(edge.target, (indegree.get(edge.target) || 0) - 1);
        if (indegree.get(edge.target) === 0) queue.push(edge.target);
      });
  }
  const counts = new Map<number, number>();
  const positions = new Map<string, { x: number; y: number }>();
  nodes.forEach((node) => {
    const level = levels.get(node.id) || 0;
    const index = counts.get(level) || 0;
    counts.set(level, index + 1);
    positions.set(node.id, { x: 32 + level * 242, y: 52 + index * 106 });
  });
  return {
    positions,
    columns: [] as { kind: string; x: number }[],
    width: Math.max(640, 300 + Math.max(0, ...levels.values()) * 242),
    height: Math.max(230, 100 + Math.max(0, ...counts.values()) * 106),
  };
}
