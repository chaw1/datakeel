import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";
import { catalogGraph } from "../../test/catalogGraph";
import { graph } from "../../test/fixtures";
import { semanticGraph } from "../../test/lineageFixtures";

import Lineage from "./Lineage";

it.each([
  ["COMPLETED", "已完成"],
  ["RUNNING", "运行中"],
  ["FAIL", "失败"],
])(
  "localizes the %s event status without changing the stored event",
  (state, label) => {
    localStorage.setItem("datakeel.locale", "zh");
    const event = { ...graph.events[0], run_state: state };
    const { container } = render(
      <I18nProvider>
        <Lineage
          graph={{
            ...graph,
            events: [event],
            edges: graph.edges.map((edge) => ({ ...edge, event })),
          }}
          focus={{ assetId: "output" }}
        />
      </I18nProvider>,
    );
    expect(container.querySelector(".event-meta .badge")).toHaveTextContent(
      label,
    );
    expect(container.querySelector(".event-detail pre")).toHaveTextContent(
      state,
    );
  },
);

it("translates catalog type columns and relationships in Chinese", () => {
  localStorage.setItem("datakeel.locale", "zh");
  const { container } = render(
    <I18nProvider>
      <Lineage
        graph={catalogGraph}
        focus={{ assetId: "retail_revenue", includeCatalog: true }}
      />
    </I18nProvider>,
  );
  expect(
    [...container.querySelectorAll(".graph-column-title")].map(
      (node) => node.textContent,
    ),
  ).toEqual(["表", "字段", "指标"]);
  expect(container.querySelector(".catalog-relations")).toHaveTextContent(
    "计算自",
  );
});

it("distinguishes catalog relationships and preserves their typed node columns", async () => {
  const { container } = render(<Lineage graph={catalogGraph} />);
  expect(container.querySelectorAll(".graph-column-title")).toHaveLength(3);
  expect(container.querySelector(".graph-edge.catalog")).toHaveAttribute(
    "marker-end",
  );
  const metric = screen.getByRole("button", { name: "Inspect Retail revenue" });
  expect(metric).toHaveAttribute("data-asset-type", "metric");
  await userEvent.click(metric);
  expect(
    screen.getByRole("region", { name: "Lineage event details" }),
  ).toHaveTextContent("measures");
});

it("distinguishes semantic similarity from lineage and shows assertion provenance", async () => {
  const user = userEvent.setup();
  const { container } = render(<Lineage graph={semanticGraph} />);
  const legend = screen.getByRole("group", { name: "Edge kinds" });
  expect(within(legend).getByText("Lineage")).toBeVisible();
  expect(within(legend).getByText("Semantic similarity")).toBeVisible();
  expect(container.querySelector(".graph-edge.lineage")).toHaveAttribute(
    "marker-end",
  );
  expect(container.querySelector(".graph-edge.semantic")).not.toHaveAttribute(
    "marker-end",
  );
  expect(screen.getByRole("status")).toHaveTextContent("bounded subgraph");
  await user.click(screen.getByRole("button", { name: "Inspect Source file" }));
  const panel = screen.getByRole("region", { name: "Lineage event details" });
  expect(within(panel).getByText("similar_to")).toBeVisible();
  expect(
    within(panel).getByText(/evidence.near_duplicate/, { selector: "p" }),
  ).toBeVisible();
  expect(within(panel).getByText("Candidate")).toBeVisible();
  expect(within(panel).getByText("text.clean")).toBeVisible();
});

it("resolves a large event from the shared event collection", async () => {
  const user = userEvent.setup();
  render(
    <Lineage
      graph={{
        ...graph,
        edges: graph.edges.map((edge) => ({ ...edge, event: null })),
      }}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Inspect Source file" }));
  expect(
    screen.getByRole("region", { name: "Lineage event details" }),
  ).toHaveTextContent("text.clean");
});

it("opens connected event evidence when a lineage node is clicked", async () => {
  const user = userEvent.setup();
  render(<Lineage graph={graph} />);
  await user.click(screen.getByRole("button", { name: "Inspect Source file" }));
  const panel = screen.getByRole("region", { name: "Lineage event details" });
  expect(within(panel).getByText("text.clean")).toBeVisible();
  expect(within(panel).getByText("event-1")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Close event details" }));
  expect(
    screen.queryByRole("region", { name: "Lineage event details" }),
  ).not.toBeInTheDocument();
});
it("supports keyboard inspection of lineage nodes", async () => {
  const user = userEvent.setup();
  render(<Lineage graph={graph} />);
  screen.getByRole("button", { name: "Inspect Cleaned file" }).focus();
  await user.keyboard("{Enter}");
  expect(
    screen.getByRole("region", { name: "Lineage event details" }),
  ).toBeVisible();
});

it("opens the receipt target when navigating from an action", () => {
  render(
    <Lineage graph={graph} focus={{ assetId: "output", eventId: "event-1" }} />,
  );
  expect(
    screen.getByRole("region", { name: "Lineage event details" }),
  ).toHaveTextContent("text.clean");
});

it("marks quarantined assets in the graph and its evidence panel", async () => {
  const user = userEvent.setup();
  render(
    <Lineage
      graph={{
        ...graph,
        nodes: graph.nodes.map((node) => ({
          ...node,
          quarantined: node.id === "output",
        })),
      }}
    />,
  );
  await user.click(
    screen.getByRole("button", { name: "Inspect Cleaned file" }),
  );
  expect(
    within(
      screen.getByRole("region", { name: "Lineage event details" }),
    ).getByText("Quarantined"),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Inspect Cleaned file" }),
  ).toHaveClass("quarantined");
});

it("stops pinning a linked receipt after the user inspects a different asset", async () => {
  const user = userEvent.setup();
  const receipt = {
    ...graph.events[0],
    event_id: "receipt-extra",
    operator: "quarantine_files",
  };
  render(
    <Lineage
      graph={{ ...graph, events: [...graph.events, receipt] }}
      focus={{ assetId: "output", eventId: "receipt-extra" }}
    />,
  );
  expect(
    within(
      screen.getByRole("region", { name: "Lineage event details" }),
    ).getByText("quarantine_files"),
  ).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Inspect Source file" }));
  expect(
    within(
      screen.getByRole("region", { name: "Lineage event details" }),
    ).queryByText("quarantine_files"),
  ).not.toBeInTheDocument();
});
