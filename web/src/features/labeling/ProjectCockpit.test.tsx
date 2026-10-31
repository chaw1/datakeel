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
        task_samples: [
          {
            task_id: "rework-task",
            sample_id: "sample-9",
            name: "dock-09.jpg",
            path: "harbor/night/dock-09.jpg",
          },
        ],
        prelabel_accuracy: {
          ...labelingProject.prelabel_accuracy,
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
  expect(screen.getByText("dock-09.jpg")).toHaveAttribute(
    "title",
    "harbor/night/dock-09.jpg",
  );
  expect(screen.queryByText("rework-task")).toBeNull();
  expect(screen.getByText("Exact-match rate: 75%")).toBeVisible();
  expect(screen.getByText("Approved reference: 3/4 tasks")).toBeVisible();
  const row = screen.getByRole("row", { name: "member 11 7 4 25%" });
  expect(within(row).getAllByRole("cell")).toHaveLength(5);
});

it("names the people column and only shows agreement sections that have pairs", () => {
  const { rerender } = render(<ProjectCockpit data={labelingProject} />);
  expect(screen.getByRole("columnheader", { name: "Annotator" })).toBeVisible();
  expect(screen.queryByText(/Current actor/)).toBeNull();
  expect(screen.queryByRole("heading", { name: /Cohen κ/ })).toBeNull();
  expect(screen.queryByRole("heading", { name: /mean IoU/ })).toBeNull();
  expect(
    screen.getByText("No overlapping annotations to compare yet."),
  ).toBeVisible();
  rerender(
    <ProjectCockpit
      data={{
        ...labelingProject,
        agreement: {
          ...labelingProject.agreement,
          boxes: [
            {
              annotator_a: "ann",
              annotator_b: "qa",
              mean_iou: 0.8,
              sample_count: 2,
              box_count_a: 2,
              box_count_b: 2,
              category_agreement: 1,
              match_rate: 1,
              matched_count: 2,
            },
          ],
        },
      }}
    />,
  );
  expect(screen.getByRole("heading", { name: /mean IoU/ })).toBeVisible();
  expect(screen.getByText("ann / qa: 0.800")).toBeVisible();
  expect(screen.queryByRole("heading", { name: /Cohen κ/ })).toBeNull();
  expect(
    screen.queryByText("No overlapping annotations to compare yet."),
  ).toBeNull();
});
