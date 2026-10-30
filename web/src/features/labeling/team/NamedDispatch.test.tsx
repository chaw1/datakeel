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
// `local` still holds harbor-001.png; harbor-002.png was taken back and waits for someone.
const leases: LeaseStatus = {
  project_id: "project",
  observed_at: "2026-10-30T00:00:00Z",
  active: [
    {
      assignment: {
        id: "assignment-1",
        task_id: "task-1",
        actor: "local",
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

beforeEach(() => {
  vi.mocked(production.readProduction).mockImplementation((name) =>
    Promise.resolve(name === "lease_status" ? leases : inProgress),
  );
  vi.mocked(production.getTaskSamples).mockResolvedValue({
    items: labelingProject.task_samples,
  });
  vi.mocked(production.getAssignees)
    .mockReset()
    .mockResolvedValue({
      project_id: "project",
      stage: "annotation",
      people: [{ actor: "ann", display_name: "Ann Lee", current: 2 }],
    });
  vi.mocked(actions.prepareProduction).mockReset();
  vi.mocked(actions.executeProduction)
    .mockReset()
    .mockResolvedValue({ status: "SUCCEEDED" } as ActionRun);
});

function mount(scopes: string[] = ["production:assign"]) {
  const changed = vi.fn();
  render(
    <ProjectCockpit
      data={team}
      can={(scope) => scopes.includes(scope)}
      onChanged={changed}
    />,
  );
  return changed;
}

it("assigns taken-back tasks to a registered person by name after a signed plan", async () => {
  const plan = {
    ...actionPlan,
    action_type: "assign_tasks" as const,
    reversible: true,
  };
  vi.mocked(actions.prepareProduction).mockResolvedValue(plan);
  const changed = mount();
  const card = await screen.findByRole("region", {
    name: "Assign to a named person",
  });
  expect(production.getAssignees).toHaveBeenCalledWith("project", "annotation");
  const free = await screen.findByRole("checkbox", { name: "harbor-002.png" });
  expect(free).toBeChecked();
  expect(card).not.toHaveTextContent("harbor-001.png");
  const prepare = screen.getByRole("button", {
    name: "Prepare assignment plan",
  });
  expect(prepare).toBeDisabled();
  fireEvent.change(screen.getByRole("combobox", { name: "Assign to" }), {
    target: { value: "ann" },
  });
  expect(
    screen.getByRole("option", { name: "Ann Lee (ann) · 2 open now" }),
  ).toBeInTheDocument();
  fireEvent.click(prepare);
  expect(await screen.findByText("1 tasks go to Ann Lee.")).toBeVisible();
  expect(actions.prepareProduction).toHaveBeenCalledWith("assign_tasks", {
    task_ids: ["task-2"],
    actor: "ann",
    stage: "annotation",
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign and assign" }));
  await waitFor(() => {
    expect(actions.executeProduction).toHaveBeenCalledWith(plan, false);
  });
  expect(changed).toHaveBeenCalled();
});

it("says who to register first when nobody can annotate yet", async () => {
  vi.mocked(production.getAssignees).mockResolvedValue({
    project_id: "project",
    stage: "annotation",
    people: [],
  });
  mount();
  expect(
    await screen.findByText(
      "Nobody registered can annotate here yet. Give someone the annotator role on this project first.",
    ),
  ).toBeVisible();
  expect(screen.queryByRole("combobox", { name: "Assign to" })).toBeNull();
});

it("shows a refused list as a readable error and hides the panel without assign scope", async () => {
  vi.mocked(production.getAssignees).mockRejectedValue(
    new ApiError(
      403,
      "Listing assignable people requires the production:assign scope",
    ),
  );
  mount();
  const card = await screen.findByRole("region", {
    name: "Assign to a named person",
  });
  await waitFor(() => {
    expect(card.querySelector("[role=alert]")).not.toBeNull();
  });
  expect(screen.queryByRole("combobox", { name: "Assign to" })).toBeNull();
});

it("keeps named assignment away from people who cannot assign", () => {
  mount([]);
  expect(
    screen.queryByRole("region", { name: "Assign to a named person" }),
  ).toBeNull();
});
