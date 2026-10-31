import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { translator } from "../../i18n/context";
import { labelingProject, labelingTask } from "../../test/labelingFixtures";

import { TaskSession } from "./TaskSession";

import type { ReactNode } from "react";

const texts = vi.hoisted<string[]>(() => []);
vi.mock("react-konva", async () => {
  const { createElement } = await import("react");
  const node = ({ children }: { children?: ReactNode }) =>
    createElement("div", null, children);
  return {
    Stage: node,
    Layer: node,
    Group: node,
    Image: node,
    Rect: node,
    Transformer: node,
    Circle: node,
    Line: node,
    Label: node,
    Tag: node,
    Text: ({ text }: { text: string }) => {
      texts.push(text);
      return null;
    },
  };
});
vi.mock("../../api/production", () => ({ getTaskWorkbench: vi.fn() }));
const t = translator("en");

it("keeps details in a collapsible drawer and names each box on the canvas", () => {
  const task = {
    ...labelingTask,
    revisions: [
      {
        id: "revision",
        task_id: "task-1",
        previous_revision_id: null,
        object_confidences: [],
        source: "human" as const,
        actor: "local",
        created_at: "2026-10-30T00:00:00Z",
        annotation: {
          sample_id: "sample-1",
          annotator_id: "local",
          image_width: 100,
          image_height: 100,
          boxes: [{ category: "cat", x1: 1, y1: 1, x2: 20, y2: 20 }],
        },
      },
    ],
    task: { ...labelingTask.task, latest_revision_id: "revision" },
  };
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
  expect(texts).toContain("Cat");
  const drawer = screen.getByRole("complementary", { name: t("wbDrawer") });
  expect(within(drawer).getByText(t("wbEditorBoxHint"))).toBeVisible();
  fireEvent.click(
    within(drawer).getByRole("button", { name: t("wbCollapseDrawer") }),
  );
  expect(
    within(drawer).getByRole("button", { name: t("wbExpandDrawer") }),
  ).toHaveAttribute("aria-expanded", "false");
  expect(within(drawer).getByText(t("wbEditorBoxHint"))).not.toBeVisible();
});
