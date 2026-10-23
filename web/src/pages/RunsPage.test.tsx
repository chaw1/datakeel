import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { dashboard } from "../test/dashboardFixtures";

import { RunsPage } from "./RunsPage";

it("merges both run types by creation time with object detail links", () => {
  render(<RunsPage data={dashboard} params={new URLSearchParams()} />);
  const rows = within(screen.getByRole("table")).getAllByRole("row");
  expect(rows).toHaveLength(3);
  expect(rows[1]).toHaveTextContent("delete_files");
  expect(within(rows[1]).getByRole("link")).toHaveAttribute(
    "href",
    "#/object/action_run/run-1?tab=relations",
  );
});
it("applies the running pipeline filter from a direct URL", () => {
  render(
    <RunsPage
      data={dashboard}
      params={new URLSearchParams("type=pipeline&state=active")}
    />,
  );
  expect(screen.getByRole("combobox")).toHaveValue("pipeline");
  expect(screen.getByRole("checkbox")).toBeChecked();
  expect(screen.queryByText("delete_files")).not.toBeInTheDocument();
  expect(screen.getAllByRole("row")).toHaveLength(2);
});

it("shows measured pipeline duration from its persisted finish time", () => {
  const original = dashboard.tasks[0];
  render(
    <RunsPage
      data={{
        ...dashboard,
        tasks: [
          {
            ...original,
            state: "COMPLETED",
            finished_at: original.created_at + 17,
          },
        ],
      }}
      params={new URLSearchParams("type=pipeline")}
    />,
  );
  const row = screen.getAllByRole("row")[1];
  expect(within(row).getAllByRole("cell")[4]).toHaveTextContent("17");
});

it("keeps an unknown duration for legacy completed tasks", () => {
  render(
    <RunsPage
      data={{
        ...dashboard,
        tasks: [
          { ...dashboard.tasks[0], state: "COMPLETED", finished_at: null },
        ],
      }}
      params={new URLSearchParams("type=pipeline")}
    />,
  );
  const row = screen.getAllByRole("row")[1];
  expect(within(row).getAllByRole("cell")[4]).toHaveTextContent("—");
});
