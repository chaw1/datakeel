import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { getTaskWorkbench } from "../../api/production";
import { labelingProject, labelingTask } from "../../test/labelingFixtures";

import { TaskSession } from "./TaskSession";

import type { TaskWorkbench } from "../../api/production";

vi.mock("../../api/production", () => ({ getTaskWorkbench: vi.fn() }));
vi.mock("./actions", () => ({
  mutateProduction: vi.fn(),
  actionDetails: vi.fn(),
}));
vi.mock("./editors/AnnotationEditor", () => ({ AnnotationEditor: () => null }));

function header(sample: Partial<TaskWorkbench["sample"]>) {
  const task = {
    ...labelingTask,
    sample: { ...labelingTask.sample, ...sample },
  };
  vi.mocked(getTaskWorkbench).mockResolvedValue(task);
  render(
    <TaskSession
      task={task}
      project={labelingProject}
      actor="local"
      canSync
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      onSnapshot={vi.fn()}
      registerGuard={vi.fn()}
    />,
  );
  return screen.getByRole("heading", { level: 2 });
}

it("names the opened task by its path under the import root, in full on hover", () => {
  const path =
    "store-07/2026-10-30/aisle-12/refrigerated-display-left-door.png";
  const heading = header({ name: "refrigerated-display-left-door.png", path });
  expect(heading.textContent).toBe(path);
  // The operation bar cuts a long path short; the title keeps all of it.
  expect(heading.getAttribute("title")).toBe(path);
});

it("names a task without a recorded path by its file name", () => {
  const heading = header({ name: "shelf.png", path: "" });
  expect(heading.textContent).toBe("shelf.png");
  expect(heading.getAttribute("title")).toBe("shelf.png");
});
