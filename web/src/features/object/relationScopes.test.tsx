import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { detail, metricObject, table, term } from "../catalog/fixtures";

import {
  objectCatalogGraph,
  objectFacts,
  objectRelationEdges,
  objectStatus,
} from "./descriptors";
import { ObjectRelations } from "./ObjectRelations";
import {
  alias,
  edge,
  fixture,
  node,
  orders,
  paidId,
  reference,
  summary,
} from "./relationScopeFixtures";

import type { ObjectTarget } from "./navigation";
import type { GraphNode } from "../../api/types";

function fact(target: ObjectTarget, label: string, data = fixture) {
  return objectFacts(data, target).find((item) => item.label === label)?.value;
}

it("counts only metrics referencing the current column and deduplicates repeated backing edges", () => {
  expect(fact({ kind: "column", id: paidId }, "objMetrics")).toBe(1);
  expect(fact({ kind: "column", id: `${orders}/date` }, "objMetrics")).toBe(3);
  expect(
    fact({ kind: "column", id: `${summary}/paid_amount` }, "objMetrics"),
  ).toBe(0);
});

it("counts only outgoing derived targets, including the current table's own columns", () => {
  expect(fact({ kind: "column", id: paidId }, "objDerived")).toBe(1);
  expect(
    fact({ kind: "column", id: `${summary}/paid_amount` }, "objDerived"),
  ).toBe(0);
  expect(fact({ kind: "table", id: orders }, "objDerived")).toBe(2);
  const summaryData = {
    ...fixture,
    table: {
      ...detail,
      table: { ...table, asset_ref: { ...table.asset_ref, asset_id: summary } },
      columns:
        fixture.table?.columns.map((item) => ({
          ...item,
          asset_ref: { ...item.asset_ref, asset_id: `${summary}/${item.name}` },
        })) ?? [],
    },
  };
  expect(fact({ kind: "table", id: summary }, "objDerived", summaryData)).toBe(
    0,
  );
});

it("keeps metric facts authoritative while filtering measures and dimensions to its outgoing edges", () => {
  const target: ObjectTarget = {
    kind: "metric",
    id: metricObject.asset_ref.asset_id,
  };
  expect(fact(target, "objDimensions")).toBe(3);
  expect(fact(target, "objMeasures")).toBe(3);
  const fields = objectRelationEdges(fixture, target, "measures");
  expect(new Set(fields.map((item) => item.target))).toHaveLength(3);
  expect(fields.every((item) => item.source === target.id)).toBe(true);
  expect(objectRelationEdges(fixture, target, "sliced_by")).toHaveLength(3);
  expect(
    objectRelationEdges(fixture, target, "sliced_by").every(
      (item) => item.source === target.id,
    ),
  ).toBe(true);
});

it("derives term counts and status from that term's own outgoing means links", () => {
  const target: ObjectTarget = { kind: "term", id: term.asset_ref.asset_id };
  expect(fact(target, "objLinkedObjects")).toBe(1);
  const data = {
    ...fixture,
    target: { kind: "term", id: "term/Orphan" } as const,
    dataset: undefined,
    catalog: term,
    metric: undefined,
  };
  expect(fact(data.target, "objLinkedObjects", data)).toBe(0);
  expect(objectStatus(data)).toBe("objOrphan");
});

it("renders only current metric dimensions in a filtered relation tab", () => {
  const { container } = render(
    <ObjectRelations
      data={fixture}
      target={{ kind: "metric", id: "retail_revenue", relation: "sliced_by" }}
      onOpen={vi.fn()}
    />,
  );
  expect(container.querySelectorAll(".graph-edge.catalog")).toHaveLength(3);
  expect(
    screen.getByRole("button", { name: "Inspect Retail revenue" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Inspect Order count" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Inspect Retail units" }),
  ).not.toBeInTheDocument();
});

it("preserves catalog names over stale reference IDs in scoped graphs and distinguishes date fields", () => {
  const projected = objectCatalogGraph(fixture);
  expect(
    projected?.nodes.find((item) => item.asset_id === "retail_revenue")
      ?.display_name,
  ).toBe("Retail revenue");
  expect(
    projected?.nodes.find((item) => item.asset_id === `${orders}/date`)
      ?.display_name,
  ).toBe("orders.date");
  expect(
    projected?.nodes.find((item) => item.asset_id === `${summary}/date`)
      ?.display_name,
  ).toBe("retail_summary.date");
  const { container } = render(
    <ObjectRelations
      data={fixture}
      target={{ kind: "table", id: orders, relation: "derived" }}
      onOpen={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Inspect orders.date" }),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Inspect retail_summary.date" }),
  ).toBeVisible();
  expect(
    [...container.querySelectorAll(".archive-prefix")].map(
      (item) => item.textContent,
    ),
  ).toEqual(expect.arrayContaining(["orders.", "retail_summary."]));
});

it("does not show incoming or neighboring derived edges for a summary column", () => {
  const { container } = render(
    <ObjectRelations
      data={fixture}
      target={{
        kind: "column",
        id: `${summary}/paid_amount`,
        relation: "derived",
      }}
      onOpen={vi.fn()}
    />,
  );
  expect(container.querySelectorAll(".graph-edge")).toHaveLength(0);
  expect(screen.getByText("No matching relationships.")).toBeVisible();
  expect(container.querySelectorAll(".graph-node")).toHaveLength(1);
});

it("keeps all seven real derived targets when the display graph folds them into aggregates", () => {
  const targets = Array.from(
    { length: 7 },
    (_, index) => `${summary}/derived-${String(index)}`,
  );
  const neighbors = {
    asset_id: orders,
    truncated: false,
    objects: [
      ...(fixture.catalogNeighbors?.objects ?? []),
      ...targets.map((id) => ({
        asset_ref: { asset_id: id, asset_type: "column", namespace: "default" },
        name: id,
        revision: 1,
        properties: {},
      })),
    ],
    links: targets.map((id) => ({
      source: reference(alias(paidId)),
      target: { asset_id: id, asset_type: "column", namespace: "default" },
      kind: "derived" as const,
    })),
  };
  const aggregate: GraphNode = {
    id: "aggregate:catalog:7",
    asset_id: "aggregate:catalog:7",
    asset_type: "aggregate",
    namespace: "graph",
    label: "More",
  };
  const data = {
    ...fixture,
    catalogNeighbors: neighbors,
    graph: {
      ...fixture.graph,
      nodes: [node(paidId, "column"), aggregate],
      edges: [edge(paidId, aggregate.id, "derived")],
      truncated: true,
    },
  };
  expect(fact({ kind: "table", id: orders }, "objDerived", data)).toBe(7);
  expect(fact({ kind: "column", id: paidId }, "objDerived", data)).toBe(7);
  expect(
    objectRelationEdges(data, { kind: "table", id: orders }, "derived"),
  ).toHaveLength(7);
  const { container } = render(
    <ObjectRelations
      data={data}
      target={{ kind: "table", id: orders, relation: "derived" }}
      onOpen={vi.fn()}
    />,
  );
  expect(container.querySelectorAll(".graph-edge.catalog")).toHaveLength(7);
});
