import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as production from "../../../api/production";
import { labelingProject } from "../../../test/labelingFixtures";
import { ProjectCockpit } from "../ProjectCockpit";

import { SkillDispatch } from "./SkillDispatch";

import type {
  PackageAcceptance,
  ProjectWorkbench,
} from "../../../api/production";

vi.mock("../../../api/production", () => ({
  readProduction: vi.fn(),
  getTaskSamples: vi.fn(),
  previewDispatch: vi.fn(),
  getAssignees: vi.fn(),
}));
vi.mock("../actions", () => ({
  prepareProduction: vi.fn(),
  executeProduction: vi.fn(),
}));

const team: ProjectWorkbench = {
  ...labelingProject,
  project: {
    ...labelingProject.project,
    workflow_tier: "team",
    skill_requirement: {
      annotation_type: "box",
      domain: "street",
      min_level: 3,
    },
  },
};
const withStates = (first: string, second: string): ProjectWorkbench => ({
  ...team,
  tasks: team.tasks.map((task, index) => ({
    ...task,
    state: (index ? second : first) as typeof task.state,
  })),
});
const accepted: PackageAcceptance = {
  project_id: "project",
  package_id: "package",
  status: "accepted",
  total: 3,
  approved: 3,
  sampling: null,
  latest: {
    id: "inspection-1",
    package_id: "package",
    defective_count: 0,
    accepted: true,
    returned_task_ids: [],
    actor: "pm",
    created_at: "2026-10-30T00:00:00Z",
    sampling: {
      lot_size: 3,
      sample_size: 3,
      sample_ids: ["sample-1", "sample-2", "sample-3"],
      task_ids: ["task-1", "task-2", "task-3"],
      acceptance_number: 0,
      rejection_number: 1,
      method: "aql",
      seed: 0,
    },
  },
  inspections: 1,
};

beforeEach(() => {
  vi.mocked(production.readProduction).mockImplementation((name) =>
    Promise.resolve(
      name === "lease_status"
        ? {
            project_id: "project",
            observed_at: "2026-10-30T00:00:00Z",
            active: [],
            overdue: [],
            reclaimed: [],
          }
        : accepted,
    ),
  );
  vi.mocked(production.getTaskSamples).mockResolvedValue({
    items: labelingProject.task_samples,
  });
  vi.mocked(production.getAssignees).mockResolvedValue({
    project_id: "project",
    stage: "annotation",
    people: [],
  });
});

const box = (name: string) => screen.getByRole("checkbox", { name });

it("resets the dispatch choice to whatever still waits after the task list refreshes", () => {
  const view = render(
    <SkillDispatch
      data={withStates("pending", "pending")}
      onChanged={vi.fn()}
    />,
  );
  fireEvent.click(box("harbor-002.png"));
  expect(screen.getByText("Tasks to dispatch (1 selected)")).toBeVisible();
  view.rerender(
    <SkillDispatch
      data={withStates("pending", "pending")}
      onChanged={vi.fn()}
    />,
  );
  expect(screen.getByText("Tasks to dispatch (1 selected)")).toBeVisible();
  // harbor-001 was dispatched: it leaves the list and the count.
  view.rerender(
    <SkillDispatch
      data={withStates("in_progress", "pending")}
      onChanged={vi.fn()}
    />,
  );
  expect(screen.getByText("Tasks to dispatch (1 selected)")).toBeVisible();
  expect(screen.queryByRole("checkbox", { name: "harbor-001.png" })).toBeNull();
  expect(box("harbor-002.png")).toBeChecked();
  // A rejected package hands harbor-001 back: it is waiting, so it is ticked.
  view.rerender(
    <SkillDispatch
      data={withStates("pending", "pending")}
      onChanged={vi.fn()}
    />,
  );
  expect(screen.getByText("Tasks to dispatch (2 selected)")).toBeVisible();
  expect(box("harbor-001.png")).toBeChecked();
  expect(box("harbor-002.png")).toBeChecked();
});

it("shows the last sample once a package has been decided", async () => {
  render(<ProjectCockpit data={team} can={() => true} onChanged={vi.fn()} />);
  const table = await screen.findByRole("table", {
    name: "Package acceptance",
  });
  expect(await screen.findByText("Checked 3 of 3")).toBeVisible();
  expect(table).not.toHaveTextContent(
    "Sample is drawn once every task is approved",
  );
});
