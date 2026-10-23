import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { graph } from "../../test/fixtures";

import { RelationList } from "./RelationList";

it("collapses groups above eight edges and still exposes every relation on expansion", async () => {
  const user = userEvent.setup();
  const edges = Array.from({ length: 9 }, (_, index) => ({
    ...graph.edges[0],
    kind: "lineage" as const,
    operator: `operation-${String(index)}`,
  }));
  render(<RelationList graph={{ ...graph, edges }} onSelect={vi.fn()} />);
  const summary = screen.getByText("Lineage · 9");
  const group = summary.closest("details");
  if (!group) throw new Error("Missing relation group");
  expect(group).not.toHaveAttribute("open");
  expect(screen.getByText("operation-8")).not.toBeVisible();
  await user.click(summary);
  expect(within(group).getAllByRole("listitem")).toHaveLength(9);
  expect(screen.getByText("operation-8")).toBeVisible();
});
