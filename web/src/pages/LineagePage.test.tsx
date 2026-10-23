import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { catalogGraph } from "../test/catalogGraph";
import { dataset, workspace } from "../test/fixtures";
import { semanticGraph } from "../test/lineageFixtures";

import { LineagePage } from "./LineagePage";
it("renders lineage nodes", () => {
  render(<LineagePage data={workspace} selectedId={dataset.id} />);
  expect(
    screen.getByRole("button", { name: "Inspect Source file" }),
  ).toBeVisible();
});

it("fetches only the bounded catalog neighborhood for an independent metric", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(catalogGraph))),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <LineagePage
      data={workspace}
      selectedId=""
      focus={{ assetId: "retail_revenue", includeCatalog: true }}
    />,
  );
  expect(
    await screen.findByRole("heading", {
      name: "Follow the metric to its source.",
    }),
  ).toBeVisible();
  expect(
    await screen.findByRole("region", { name: "Lineage event details" }),
  ).toHaveTextContent("measures");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch).toHaveBeenCalledWith(
    "/api/lineage/graph?asset_id=retail_revenue&include_catalog=true&hops=2&max_nodes=30",
    expect.objectContaining({ method: "GET" }),
  );
});

it("loads a bounded semantic subgraph when opened from a sample", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(semanticGraph))),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <LineagePage
      data={workspace}
      selectedId={dataset.id}
      focus={{ assetId: "source", includeSemantic: true }}
    />,
  );
  expect(
    await screen.findByRole("region", { name: "Lineage event details" }),
  ).toHaveTextContent("similar_to");
  expect(fetch).toHaveBeenCalledWith(
    "/api/lineage/graph?asset_id=source&include_semantic=true&hops=2&max_nodes=200",
    expect.objectContaining({ method: "GET" }),
  );
});
