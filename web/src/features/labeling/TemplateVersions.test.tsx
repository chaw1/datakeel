import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { actionPlan } from "../../test/actionFixtures";
import { labelingProject } from "../../test/labelingFixtures";

import * as actions from "./actions";
import { ProjectCockpit } from "./ProjectCockpit";
import { templateVersions } from "./TemplateVersions";

import type { ProjectWorkbench } from "../../api/production";
import type { ActionPlan, ActionRun } from "../../api/types";

vi.mock("./actions", () => ({
  prepareProduction: vi.fn(),
  executeProduction: vi.fn(),
}));

const { template } = labelingProject;
if (!template) throw new Error("The labeling fixture has a template");
const newer: ProjectWorkbench = {
  ...labelingProject,
  project: { ...labelingProject.project, template_version: 1 },
  latest_template: { ...template, revision: 2 },
  latest_label_set_version: 2,
};
const upgrade = {
  project_id: "project",
  template_id: "template",
  from_template_version: 1,
  to_template_version: 2,
  label_set_id: "labels",
  from_label_set_version: 1,
  to_label_set_version: 2,
  labels: { added: ["bird"], removed: ["dog"], renamed: [], changed: [] },
  attributes: {
    added: ["object:colour"],
    removed: [],
    changed: [],
    required: ["object:colour"],
  },
  settings_changed: [],
  task_count: 2,
  annotated_task_count: 1,
  annotation_object_count: 2,
  invalid_task_count: 1,
  invalid_object_count: 2,
  invalid_tasks: [
    {
      task_id: "task-1",
      revision_id: "revision-1",
      sample_id: "sample-1",
      state: "in_progress",
      invalid_objects: 2,
      problems: ['box 1 label "dog" is not in label set v2'],
    },
  ],
};
const plan: ActionPlan = {
  ...actionPlan,
  action_type: "upgrade_project_template",
  canonical_params: { project_id: "project" },
  manifest: {
    ...actionPlan.manifest,
    objects: [
      {
        asset_ref: {
          asset_id: "project",
          asset_type: "project",
          namespace: "default",
        },
        revision: "r",
        state_revision: 0,
        properties: { template_upgrade: upgrade },
        size: 0,
      },
    ],
  },
};

beforeEach(() => {
  vi.mocked(actions.prepareProduction).mockReset().mockResolvedValue(plan);
  vi.mocked(actions.executeProduction)
    .mockReset()
    .mockResolvedValue({ status: "SUCCEEDED" } as ActionRun);
});

it("reports locked and newest versions and stays quiet when nothing is newer", () => {
  expect(templateVersions(labelingProject)).toMatchObject({
    current: 1,
    latest: 1,
    newer: false,
  });
  expect(templateVersions(newer)).toMatchObject({
    current: 1,
    latest: 2,
    labels: 1,
    latestLabels: 2,
    newer: true,
  });
  const archived = {
    ...newer,
    latest_template: { ...template, revision: 2, archived: true },
    latest_label_set_version: 1,
  };
  expect(templateVersions(archived).newer).toBe(false);
  render(<ProjectCockpit data={labelingProject} can={() => true} />);
  expect(
    screen.getByText("Current template v1, latest v1"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Prepare upgrade" }),
  ).not.toBeInTheDocument();
});

it("prepares, explains and signs an upgrade for a manager only", async () => {
  const onChanged = vi.fn();
  const { rerender } = render(
    <ProjectCockpit data={newer} can={() => false} onChanged={onChanged} />,
  );
  expect(
    screen.getByText("Current template v1, latest v2"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Prepare upgrade" }),
  ).not.toBeInTheDocument();
  rerender(
    <ProjectCockpit
      data={newer}
      can={(scope) => scope === "production:manage"}
      onChanged={onChanged}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Prepare upgrade" }));
  await screen.findByRole("dialog", {
    name: "Upgrade this project's template",
  });
  expect(actions.prepareProduction).toHaveBeenCalledWith(
    "upgrade_project_template",
    { project_id: "project" },
  );
  expect(
    screen.getByText("Template v1 → v2; labels v1 → v2"),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "Attributes added: object:colour; removed: none; changed: none; newly required: object:colour",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "1 existing annotation (2 objects) would not pass the new version:",
    ),
  ).toBeInTheDocument();
  expect(actions.executeProduction).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Sign and upgrade" }));
  await waitFor(() => {
    expect(actions.executeProduction).toHaveBeenCalledWith(plan, true);
  });
  expect(onChanged).toHaveBeenCalled();
  expect(
    await screen.findByText("Upgraded. This project now uses template v2."),
  ).toBeInTheDocument();
});
