import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { labelingProject } from "../../test/labelingFixtures";

import * as actions from "./actions";
import { TemplateEditor } from "./TemplateEditor";

import type {
  ProductionTemplate,
  ProjectWorkbench,
} from "../../api/production";
import type { ActionRun } from "../../api/types";

vi.mock("./actions", async (original) => ({
  ...(await original<typeof actions>()),
  mutateProduction: vi.fn(),
}));

it("builds the next version from the newest revision, not the project's locked one", async () => {
  const { template } = labelingProject;
  if (!template) throw new Error("The labeling fixture has a template");
  const data: ProjectWorkbench = {
    ...labelingProject,
    latest_template: { ...template, name: "Boxes v2", revision: 2 },
  };
  vi.mocked(actions.mutateProduction).mockResolvedValue({
    status: "SUCCEEDED",
    receipt: { quality: { details: { revision: 3 } } },
  } as unknown as ActionRun);
  const changed = vi.fn();
  render(<TemplateEditor project={data} onChanged={changed} />);
  expect(screen.getByText("Boxes v2 · Template version 2")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Save template version" }),
  );
  expect(
    await screen.findByText(
      "Saved as template v3. Projects keep their locked version; upgrade each one from its cockpit.",
    ),
  ).toBeInTheDocument();
  const [name, values] = vi.mocked(actions.mutateProduction).mock.calls[0];
  expect(name).toBe("create_label_set");
  expect(values).toMatchObject({ target: "template", operation: "update" });
  expect(values.template).toMatchObject({ name: "Boxes v2", revision: 2 });
  expect(changed).toHaveBeenCalled();
});
it("edits ordered points and typed edges without raw schema JSON", async () => {
  const { template } = labelingProject;
  if (!template) throw new Error("The labeling fixture has a template");
  const data: ProjectWorkbench = {
    ...labelingProject,
    latest_template: {
      ...template,
      annotation_type: "keypoints",
      component_config: { components: ["keypoints"] },
      keypoint_schema: {
        points: [{ id: "nose", name: "Nose", required: true }],
        edges: [],
      },
    },
  };
  vi.mocked(actions.mutateProduction).mockResolvedValue({
    status: "SUCCEEDED",
    receipt: { quality: { details: { revision: 3 } } },
  } as unknown as ActionRun);
  render(<TemplateEditor project={data} onChanged={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Add point" }));
  fireEvent.change(
    screen.getAllByLabelText("Display name", { exact: true })[0],
    {
      target: { value: "Renamed nose" },
    },
  );
  const idFields = screen.getAllByLabelText("Stable point ID");
  fireEvent.change(idFields[1], { target: { value: "neck" } });
  fireEvent.click(screen.getByRole("button", { name: "Add edge" }));
  fireEvent.click(screen.getAllByRole("button", { name: "Move up" })[1]);
  fireEvent.click(
    screen.getByRole("button", { name: "Save template version" }),
  );
  await screen.findByText(/Saved as template v3/);
  const [, values] =
    vi.mocked(actions.mutateProduction).mock.calls.at(-1) ?? [];
  const submitted = values?.template as ProductionTemplate | undefined;
  expect(submitted?.keypoint_schema).toMatchObject({
    points: [
      { id: "neck", required: false },
      { id: "nose", name: "Renamed nose", required: true },
    ],
    edges: [["nose", "neck"]],
  });
});

it("rejects duplicate point IDs before saving a template version", () => {
  const { template } = labelingProject;
  if (!template) throw new Error("The labeling fixture has a template");
  const data: ProjectWorkbench = {
    ...labelingProject,
    latest_template: {
      ...template,
      annotation_type: "keypoints",
      component_config: { components: ["keypoints"] },
      keypoint_schema: {
        points: [
          { id: "same", name: "One", required: true },
          { id: "same", name: "Two", required: false },
        ],
        edges: [],
      },
    },
  };
  vi.mocked(actions.mutateProduction).mockClear();
  render(<TemplateEditor project={data} onChanged={vi.fn()} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Save template version" }),
  );
  expect(screen.getByRole("alert")).toHaveTextContent("unique IDs");
  expect(actions.mutateProduction).not.toHaveBeenCalled();
});
