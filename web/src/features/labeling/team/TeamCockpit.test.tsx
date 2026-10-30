import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../../api/client";
import * as production from "../../../api/production";
import { actionPlan } from "../../../test/actionFixtures";
import { labelingProject } from "../../../test/labelingFixtures";
import * as actions from "../actions";
import { ProjectCockpit } from "../ProjectCockpit";

import type {
  LeaseStatus,
  PackageAcceptance,
  ProjectWorkbench,
} from "../../../api/production";
import type { ActionRun } from "../../../api/types";

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
  project: { ...labelingProject.project, workflow_tier: "team" },
};
const skilled: ProjectWorkbench = {
  ...team,
  project: {
    ...team.project,
    skill_requirement: {
      annotation_type: "box",
      domain: "street",
      min_level: 3,
    },
  },
};
const sampling = {
  lot_size: 2,
  sample_size: 2,
  sample_ids: ["sample-1", "sample-2"],
  task_ids: ["task-1", "task-2"],
  acceptance_number: 0,
  rejection_number: 1,
  method: "aql" as const,
  seed: 0,
};
const ready: PackageAcceptance = {
  project_id: "project",
  package_id: "package",
  status: "ready",
  total: 2,
  approved: 2,
  sampling,
  latest: null,
  inspections: 0,
};
const leases: LeaseStatus = {
  project_id: "project",
  observed_at: "2026-10-30T00:00:00Z",
  active: [
    {
      assignment: {
        id: "assignment-1",
        task_id: "task-1",
        actor: "ann-1",
        stage: "annotation",
        active: true,
        created_at: "2026-10-30T00:00:00Z",
        lease_expires_at: "2026-10-30T00:10:00Z",
      },
      seconds_remaining: 290,
    },
  ],
  overdue: [],
  reclaimed: [],
};

beforeEach(() => {
  vi.mocked(production.readProduction).mockImplementation((name) =>
    Promise.resolve(name === "lease_status" ? leases : ready),
  );
  vi.mocked(production.getTaskSamples).mockResolvedValue({
    items: labelingProject.task_samples,
  });
  vi.mocked(production.getAssignees).mockResolvedValue({
    project_id: "project",
    stage: "annotation",
    people: [],
  });
  vi.mocked(actions.prepareProduction).mockReset();
  vi.mocked(actions.executeProduction)
    .mockReset()
    .mockResolvedValue({ status: "SUCCEEDED" } as ActionRun);
});

function mount(scopes: string[], data: ProjectWorkbench = team) {
  const changed = vi.fn();
  render(
    <ProjectCockpit
      data={data}
      can={(scope) => scopes.includes(scope)}
      onChanged={changed}
    />,
  );
  return changed;
}

it("shows each package's acceptance state and inspects the sample before signing", async () => {
  const plan = { ...actionPlan, action_type: "accept_package" as const };
  vi.mocked(actions.prepareProduction).mockResolvedValue(plan);
  const changed = mount(["production:accept"]);
  const table = await screen.findByRole("table", {
    name: "Package acceptance",
  });
  expect(table).toHaveTextContent("Ready for acceptance");
  expect(table).toHaveTextContent("2 / 2");
  expect(table).toHaveTextContent("Check 2, at most 0 may fail");
  fireEvent.click(screen.getByRole("button", { name: "Accept package" }));
  fireEvent.click(
    await screen.findByRole("checkbox", {
      name: "harbor-001.png has problems",
    }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare acceptance plan" }),
  );
  expect(
    screen.getByText(
      "Say what is wrong for every task marked as having problems.",
    ),
  ).toBeVisible();
  fireEvent.change(
    screen.getByRole("textbox", { name: "What is wrong with harbor-001.png" }),
    { target: { value: "Missed a boat" } },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare acceptance plan" }),
  );
  expect(
    await screen.findByText(
      "Result: the package is rejected and all 2 tasks go back for rework",
    ),
  ).toBeVisible();
  expect(actions.prepareProduction).toHaveBeenCalledWith("accept_package", {
    package_id: "package",
    checks: [
      { sample_id: "sample-1", defective: true, reason: "Missed a boat" },
      { sample_id: "sample-2", defective: false, reason: "" },
    ],
  });
  expect(actions.executeProduction).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "Sign and record decision" }),
  );
  await waitFor(() => {
    expect(actions.executeProduction).toHaveBeenCalledWith(plan, true);
  });
  expect(changed).toHaveBeenCalledOnce();
});

it("previews a skill dispatch per person with reasons, then signs the plan", async () => {
  const plan = {
    ...actionPlan,
    action_type: "assign_tasks" as const,
    reversible: true,
  };
  vi.mocked(production.previewDispatch).mockResolvedValue({
    project_id: "project",
    stage: "annotation",
    skill_requirement: {
      annotation_type: "box",
      domain: "street",
      min_level: 3,
    },
    max_active_tasks: 1,
    qualified: ["ann-1"],
    picks: [{ task_id: "task-1", actor: "ann-1" }],
    people: [{ actor: "ann-1", current: 0, added: 1 }],
    unassigned: [{ task_id: "task-2", reason: "load_limit_reached" }],
  });
  vi.mocked(actions.prepareProduction).mockResolvedValue(plan);
  mount(["production:assign"], skilled);
  fireEvent.change(
    screen.getByRole("spinbutton", {
      name: "At most this many open tasks per person",
    }),
    { target: { value: "1" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Preview dispatch" }));
  expect(
    await screen.findByText(
      "harbor-002.png: every qualified person is at the cap",
    ),
  ).toBeVisible();
  expect(production.previewDispatch).toHaveBeenCalledWith("project", {
    task_ids: ["task-1", "task-2"],
    stage: "annotation",
    candidates: [],
    max_active_tasks: 1,
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare dispatch plan" }),
  );
  expect(await screen.findByText("ann-1 gets 1 tasks")).toBeVisible();
  expect(screen.getByText("1 tasks stay undispatched")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Sign and dispatch" }));
  await waitFor(() => {
    expect(actions.executeProduction).toHaveBeenCalledWith(plan, false);
  });
});

it("takes a task back after a signed plan and explains a concurrent change", async () => {
  vi.mocked(actions.prepareProduction).mockResolvedValue({
    ...actionPlan,
    action_type: "revoke_assignment",
    reversible: true,
  });
  vi.mocked(actions.executeProduction).mockRejectedValueOnce(
    new ApiError(409, "409 Action target state changed after preparation"),
  );
  mount(["production:assign"]);
  const holders = await screen.findByRole("table", { name: "Who holds what" });
  await waitFor(() => {
    expect(holders).toHaveTextContent("harbor-001.png");
  });
  expect(holders).toHaveTextContent("ann-1");
  expect(holders).toHaveTextContent("5 min");
  fireEvent.click(screen.getByRole("button", { name: "Take back" }));
  fireEvent.change(
    screen.getByRole("textbox", {
      name: "Why take harbor-001.png back from ann-1?",
    }),
    { target: { value: "Out sick" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Prepare plan" }));
  expect(
    await screen.findByText(
      "Take harbor-001.png back from ann-1. Every saved revision is kept; the task can be claimed again.",
    ),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Sign and take back" }));
  expect(
    await screen.findByText(
      "Someone else just changed this task. Your edits are kept; try the action again.",
    ),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() => {
    expect(actions.prepareProduction).toHaveBeenCalledTimes(2);
  });
});

it("keeps team panels away from personal projects and read-only people", () => {
  render(<ProjectCockpit data={labelingProject} />);
  expect(
    screen.queryByRole("table", { name: "Package acceptance" }),
  ).toBeNull();
  expect(screen.queryByRole("button", { name: "Preview dispatch" })).toBeNull();
});

it("explains that skill dispatch needs a project skill requirement instead of failing", () => {
  mount(["production:assign"]);
  expect(
    screen.getByText(
      "This project has no skill requirement yet, so nobody can be matched by skill. Assign tasks to a named person below.",
    ),
  ).toBeVisible();
  expect(screen.queryByRole("button", { name: "Preview dispatch" })).toBeNull();
  expect(production.previewDispatch).not.toHaveBeenCalled();
});
