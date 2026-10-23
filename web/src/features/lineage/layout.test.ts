import { expect, it } from "vitest";

import { catalogGraph } from "../../test/catalogGraph";
import { graph } from "../../test/fixtures";

import { layoutGraph } from "./layout";

it("places catalog types in stable columns and sorts asset IDs within each column", () => {
  const layout = layoutGraph(catalogGraph.nodes, catalogGraph.edges);
  expect(layout.columns.map((column) => column.kind)).toEqual([
    "table",
    "column",
    "metric",
  ]);
  expect(layout.positions.get("table")?.x).toBeLessThan(
    layout.positions.get("column-a")?.x ?? 0,
  );
  expect(layout.positions.get("column-a")?.x).toBe(
    layout.positions.get("column-b")?.x,
  );
  expect(layout.positions.get("column-a")?.y).toBeLessThan(
    layout.positions.get("column-b")?.y ?? 0,
  );
  expect(layout.positions).toEqual(
    layoutGraph(
      [...catalogGraph.nodes].reverse(),
      [...catalogGraph.edges].reverse(),
    ).positions,
  );
  expect(layoutGraph(graph.nodes, graph.edges).columns).toEqual([]);
});
