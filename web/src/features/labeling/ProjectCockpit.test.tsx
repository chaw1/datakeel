import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { labelingProject } from "../../test/labelingFixtures";

import { ProjectCockpit } from "./ProjectCockpit";

it("renders counters, rework identities and workload without recomputing facts", () => {
  render(
    <ProjectCockpit
      data={{
        ...labelingProject,
        progress: {
          ...labelingProject.progress,
          total: 37,
          counts: [{ state: "approved", count: 29 }],
          rework_task_ids: ["rework-task"],
        },
        prelabel_accuracy: {
          project_id: "project",
          assessed_tasks: 4,
          exact_match_tasks: 3,
          exact_match_rate: 0.75,
        },
        workload: {
          project_id: "project",
          annotators: [
            {
              actor: "member",
              assigned: 11,
              completed: 7,
              rework_count: 2,
              review_count: 4,
              rework_rate: 0.25,
            },
          ],
        },
      }}
    />,
  );
  expect(screen.getByText("37")).toBeVisible();
  expect(screen.getByText("29")).toBeVisible();
  expect(screen.getByText("rework-task")).toBeVisible();
  expect(screen.getByText("75%")).toBeVisible();
  expect(screen.getByText("Approved reference: 3/4 tasks")).toBeVisible();
  const row = screen.getByRole("row", { name: "member 11 7 4 25%" });
  expect(within(row).getAllByRole("cell")).toHaveLength(5);
});
