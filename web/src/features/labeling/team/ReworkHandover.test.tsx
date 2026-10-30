import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as production from "../../../api/production";
import { actionPlan } from "../../../test/actionFixtures";
import { labelingProject } from "../../../test/labelingFixtures";
import * as actions from "../actions";
import { ProjectCockpit } from "../ProjectCockpit";

import { planHandovers } from "./handovers";

import type {
  LeaseStatus,
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

// Both tasks are free; task-2 is a rework round that bob annotated before it was taken back.
const team: ProjectWorkbench = {
  ...labelingProject,
  tasks: labelingProject.tasks.map((task) =>
    task.id === "task-2" ? { ...task, round: 1, annotator_id: "bob" } : task,
  ),
  project: {
    ...labelingProject.project,
    workflow_tier: "team",
    skill_requirement: {
      annotation_type: "box",
      domain: "street",
      min_level: 1,
    },
  },
};
const idle: LeaseStatus = {
  project_id: "project",
  observed_at: "2026-10-30T00:00:00Z",
  active: [],
  overdue: [],
  reclaimed: [],
};
const inProgress: PackageAcceptance = {
  project_id: "project",
  package_id: "package",
  status: "in_progress",
  total: 2,
  approved: 0,
  sampling: null,
  latest: null,
  inspections: 0,
};
const handover = {
  task_id: "task-2",
  round: 1,
  from_actor: "bob",
  to_actor: "ann",
};
const sentence =
  "Rework harbor-002.png (round 1) is handed over from its original annotator bob to ann.";

beforeEach(() => {
  vi.mocked(production.readProduction).mockImplementation((name) =>
    Promise.resolve(name === "lease_status" ? idle : inProgress),
  );
  vi.mocked(production.getTaskSamples).mockResolvedValue({
    items: labelingProject.task_samples,
  });
  vi.mocked(production.getAssignees).mockResolvedValue({
    project_id: "project",
    stage: "annotation",
    people: [{ actor: "ann", display_name: "ann", current: 0 }],
  });
  vi.mocked(actions.prepareProduction).mockReset();
});

function mount() {
  render(
    <ProjectCockpit
      data={team}
      can={(scope) => scope === "production:assign"}
      onChanged={vi.fn()}
    />,
  );
}

it("reads only well-formed handovers from a prepared plan", () => {
  const plan = {
    ...actionPlan,
    canonical_params: { transfers: [handover, { task_id: "x" }, "bad"] },
  };
  expect(planHandovers(plan)).toEqual([handover]);
  expect(planHandovers(actionPlan)).toEqual([]);
});

it("names the original annotator in a named plan that hands rework over", async () => {
  vi.mocked(actions.prepareProduction).mockResolvedValue({
    ...actionPlan,
    action_type: "assign_tasks",
    reversible: true,
    canonical_params: {
      task_ids: ["task-2"],
      actor: "ann",
      stage: "annotation",
      transfers: [handover],
    },
  });
  mount();
  await screen.findByRole("combobox", { name: "Assign to" });
  fireEvent.change(screen.getByRole("combobox", { name: "Assign to" }), {
    target: { value: "ann" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare assignment plan" }),
  );
  expect(await screen.findByText(sentence)).toBeVisible();
});

it("names the original annotator when a skill dispatch hands rework over", async () => {
  vi.mocked(production.previewDispatch).mockResolvedValue({
    project_id: "project",
    stage: "annotation",
    skill_requirement: {
      annotation_type: "box",
      domain: "street",
      min_level: 1,
    },
    max_active_tasks: null,
    qualified: ["ann"],
    picks: [
      { task_id: "task-1", actor: "ann", transferred_from: null },
      { task_id: "task-2", actor: "ann", transferred_from: "bob" },
    ],
    people: [{ actor: "ann", current: 0, added: 2 }],
    unassigned: [],
  });
  vi.mocked(actions.prepareProduction).mockResolvedValue({
    ...actionPlan,
    action_type: "assign_tasks",
    reversible: true,
  });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Preview dispatch" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Prepare dispatch plan" }),
  );
  expect(await screen.findByText("ann gets 2 tasks")).toBeVisible();
  expect(screen.getByText(sentence)).toBeVisible();
  expect(screen.getAllByText(/handed over/)).toHaveLength(1);
});
