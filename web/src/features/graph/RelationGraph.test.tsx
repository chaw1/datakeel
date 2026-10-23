import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { graph } from "../../test/fixtures";

import { RelationGraph } from "./RelationGraph";

import type { Graph, GraphNode } from "../../api/types";

const runIds = [
  "a9100e67-a084-4cdd-8b80-9ce3a4d32424",
  "a9100e67-a084-4cdd-8b80-9ce3a4d32425",
  "a9100e67-a084-4cdd-8b80-9ce3a4d32426",
];
const runs: GraphNode[] = runIds.map((id) => ({
  id,
  asset_id: id,
  asset_type: "action_run",
  namespace: "default",
  label: "decide_assertions",
  display_name: "decide_assertions",
}));
const runGraph: Graph = {
  ...graph,
  nodes: [graph.nodes[0], ...runs],
  edges: runs.map((run, index) => ({
    ...graph.edges[0],
    source: graph.nodes[0].id,
    target: run.id,
    event_id: `event-${String(index)}`,
  })),
};

it("shows one action archive card with a count and lists all IDs only on hover", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <RelationGraph graph={runGraph} focus={{ assetId: "source" }} />,
  );
  const card = screen.getByRole("button", {
    name: "Inspect decide_assertions",
  });
  expect(card).toHaveTextContent("×3");
  expect(card).toHaveTextContent("3 links");
  expect(container.querySelectorAll(".graph-node")).toHaveLength(2);
  expect(
    screen.getByRole("button", { name: "Inspect Source file" }),
  ).toHaveClass("center");
  expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  for (const id of runIds) expect(card).not.toHaveTextContent(id);
  await user.hover(card);
  const tooltip = screen.getByRole("tooltip");
  for (const id of runIds) expect(tooltip).toHaveTextContent(id);
  const writeText = vi.spyOn(navigator.clipboard, "writeText");
  await user.click(
    within(tooltip).getAllByRole("button", { name: "Copy ID" })[0],
  );
  expect(tooltip.isConnected).toBe(true);
  expect(writeText).toHaveBeenCalledWith(runIds[0]);
  expect(within(tooltip).getByRole("button", { name: "Copied" })).toBeVisible();
  await user.click(card);
  const expanded = screen.getByRole("region", {
    name: "decide_assertions · 3 runs",
  });
  expect(
    within(expanded).getAllByRole("button", { name: /^Copy ID/ }),
  ).toHaveLength(3);
});

it("loads and reveals actual hidden neighbors when an aggregate is opened", async () => {
  const user = userEvent.setup();
  const aggregate: GraphNode = {
    id: "aggregate:lineage:2",
    asset_id: "aggregate:lineage:2",
    asset_type: "aggregate",
    namespace: "graph",
    label: "aggregate:lineage:2",
  };
  const hidden = ["a", "b"].map((id) => ({
    ...graph.nodes[1],
    id,
    asset_id: id,
    label: `${id}.png`,
  }));
  const full = {
    ...graph,
    nodes: [graph.nodes[0], ...hidden],
    edges: hidden.map((node) => ({
      ...graph.edges[0],
      source: "source",
      target: node.id,
    })),
  };
  const loadExpansion = vi.fn().mockResolvedValue(full);
  const onNavigate = vi.fn();
  render(
    <RelationGraph
      graph={{
        ...graph,
        nodes: [graph.nodes[0], aggregate],
        edges: [{ ...graph.edges[0], target: aggregate.id }],
        truncated: true,
      }}
      loadExpansion={loadExpansion}
      onNavigate={onNavigate}
    />,
  );
  await user.click(
    screen.getByRole("button", { name: "Inspect Another 2 · Lineage" }),
  );
  const expanded = await screen.findByRole("region", {
    name: "Expand Lineage relationships",
  });
  expect(loadExpansion).toHaveBeenCalledOnce();
  expect(expanded).toHaveTextContent("a.png");
  expect(expanded).toHaveTextContent("b.png");
  await user.click(
    within(expanded).getAllByRole("button", { name: "Open object" })[0],
  );
  expect(onNavigate).toHaveBeenCalledWith(hidden[0]);
});

it("keeps the canvas bounded while grouping all three relationship kinds", () => {
  const nodes = Array.from({ length: 35 }, (_, index) => ({
    ...graph.nodes[0],
    id: `file-${String(index)}`,
    asset_id: `file-${String(index)}`,
    label: `file-${String(index)}.png`,
  }));
  const edges = nodes.slice(1).map((node, index) => ({
    ...graph.edges[0],
    source: nodes[0].id,
    target: node.id,
    kind: (["lineage", "semantic", "catalog"] as const)[index % 3],
  }));
  const { container } = render(
    <RelationGraph graph={{ ...graph, nodes, edges }} />,
  );
  expect(container.querySelectorAll(".graph-node").length).toBeLessThanOrEqual(
    25,
  );
  expect(
    container.querySelectorAll(".archive-relations > details"),
  ).toHaveLength(3);
  for (const kind of ["lineage", "semantic", "catalog"])
    expect(container.querySelector(`.graph-edge.${kind}`)).not.toBeNull();
});
