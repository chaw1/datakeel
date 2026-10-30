import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { ApiError } from "../../../api/client";
import { actionPlan } from "../../../test/actionFixtures";
import { labelingProject } from "../../../test/labelingFixtures";
import * as actions from "../actions";
import { ProjectCockpit } from "../ProjectCockpit";

import type { ProjectWorkbench } from "../../../api/production";
import type { ActionRun } from "../../../api/types";

// Team cards beside this one read leases and packages; keep those reads pending.
vi.mock("../../../api/production", () => ({
  readProduction: vi.fn(() => new Promise(() => undefined)),
  getTaskSamples: vi.fn(() => new Promise(() => undefined)),
  previewDispatch: vi.fn(),
  getAssignees: vi.fn(() => new Promise(() => undefined)),
}));
vi.mock("../actions", () => ({
  prepareProduction: vi.fn(),
  executeProduction: vi.fn(),
}));

const group: ProjectWorkbench = {
  ...labelingProject,
  project: {
    ...labelingProject.project,
    workflow_tier: "group",
    review_sample_rate: 0.5,
  },
};

beforeEach(() => {
  vi.mocked(actions.prepareProduction).mockReset();
  vi.mocked(actions.executeProduction)
    .mockReset()
    .mockResolvedValue({ status: "SUCCEEDED" } as ActionRun);
});

function mount(
  data: ProjectWorkbench = group,
  scopes: string[] = ["production:manage"],
) {
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

function change(percent: string) {
  fireEvent.change(screen.getByRole("spinbutton", { name: "New ratio (%)" }), {
    target: { value: percent },
  });
  fireEvent.click(screen.getByRole("button", { name: "Change ratio" }));
}

it("signs a lower review ratio after saying that exempt submissions are audited", async () => {
  const plan = {
    ...actionPlan,
    action_type: "configure_project" as const,
    reversible: false,
  };
  vi.mocked(actions.prepareProduction).mockResolvedValue(plan);
  const changed = mount();
  expect(
    screen.getByText(
      "Low-risk submissions reviewed now: 50%. High-risk submissions are always reviewed.",
    ),
  ).toBeVisible();
  change("20");
  const signer = await screen.findByRole("dialog", {
    name: "Lower review sampling",
  });
  expect(actions.prepareProduction).toHaveBeenCalledWith("configure_project", {
    project_id: "project",
    review_sample_rate: 0.2,
  });
  expect(signer).toHaveTextContent("From 50% to 20%.");
  expect(signer).toHaveTextContent(
    "every skipped review is written to the audit log",
  );
  expect(actions.executeProduction).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Sign and lower" }));
  await waitFor(() => {
    expect(actions.executeProduction).toHaveBeenCalledWith(plan, true);
  });
  expect(changed).toHaveBeenCalledOnce();
});

it("raises the ratio without a signature and shows a refused change as an error", async () => {
  const plan = {
    ...actionPlan,
    action_type: "configure_project" as const,
    reversible: true,
  };
  vi.mocked(actions.prepareProduction).mockResolvedValue(plan);
  const changed = mount();
  change("80");
  await waitFor(() => {
    expect(actions.executeProduction).toHaveBeenCalledWith(plan, false);
  });
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(changed).toHaveBeenCalledOnce();
  vi.mocked(actions.prepareProduction).mockRejectedValue(
    new ApiError(403, "Configuring a project requires production:manage"),
  );
  change("90");
  expect(await screen.findByRole("alert")).toBeVisible();
});

it("refuses ratios outside (0, 100] before asking the server", () => {
  mount();
  const button = screen.getByRole("button", { name: "Change ratio" });
  for (const value of ["0", "-5", "150", ""]) {
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "New ratio (%)" }),
      { target: { value } },
    );
    expect(button).toBeDisabled();
  }
  expect(actions.prepareProduction).not.toHaveBeenCalled();
});

it("only shows the ratio to managers of group and team projects", () => {
  mount(labelingProject);
  expect(screen.queryByRole("region", { name: "Review sampling" })).toBeNull();
  mount(group, ["production:assign"]);
  expect(screen.queryByRole("region", { name: "Review sampling" })).toBeNull();
  mount({
    ...group,
    project: { ...group.project, workflow_tier: "team" },
  });
  expect(screen.getByRole("region", { name: "Review sampling" })).toBeVisible();
});
