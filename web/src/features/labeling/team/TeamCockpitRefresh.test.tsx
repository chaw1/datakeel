import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as production from "../../../api/production";
import { labelingProject } from "../../../test/labelingFixtures";
import { ProjectCockpit } from "../ProjectCockpit";

import type {
  PackageAcceptance,
  ProjectWorkbench,
} from "../../../api/production";

vi.mock("../../../api/production", () => ({
  readProduction: vi.fn(),
  getTaskSamples: vi.fn(),
  previewDispatch: vi.fn(),
}));
vi.mock("../actions", () => ({
  prepareProduction: vi.fn(),
  executeProduction: vi.fn(),
}));

const team: ProjectWorkbench = {
  ...labelingProject,
  project: { ...labelingProject.project, workflow_tier: "team" },
};
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
