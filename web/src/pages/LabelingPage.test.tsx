import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as production from "../api/production";
import { I18nContext, translator } from "../i18n/context";
import { labelingIndex, labelingProject } from "../test/labelingFixtures";

import { LabelingPage } from "./LabelingPage";

vi.mock("../api/production", () => ({
  getWorkbench: vi.fn(),
  getProjectWorkbench: vi.fn(),
  getTaskWorkbench: vi.fn(),
}));
vi.mock("../features/labeling/editors/AnnotationEditor", () => ({
  AnnotationEditor: () => null,
}));
beforeEach(() => {
  sessionStorage.clear();
  vi.mocked(production.getWorkbench).mockResolvedValue(labelingIndex);
  vi.mocked(production.getProjectWorkbench).mockResolvedValue(labelingProject);
});
it("shows personal data counts from P29 projections without assignment or review controls", async () => {
  render(<LabelingPage params={new URLSearchParams()} />);
  await screen.findByRole("heading", { name: "My data" });
  expect(screen.getByText("Project progress · 0/2")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Open task harbor-001.png" }),
  ).toBeVisible();
  expect(screen.queryByRole("button", { name: "Claim next task" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Review queue" })).toBeNull();
});
it("uses effective project scopes for reviewer navigation and hides finalize/manage controls", async () => {
  const project = {
    ...labelingProject,
    project: { ...labelingProject.project, workflow_tier: "group" as const },
    effective_scopes: {
      actor: "reviewer",
      zero_users: false,
      scopes: ["production:review", "production:claim"],
    },
  };
  vi.mocked(production.getWorkbench).mockResolvedValue({
    ...labelingIndex,
    actor: "reviewer",
    zero_users: false,
    projects: [project.project],
    effective_scopes: project.effective_scopes,
  });
  vi.mocked(production.getProjectWorkbench).mockResolvedValue(project);
  render(<LabelingPage params={new URLSearchParams()} />);
  const review = await screen.findByRole("button", { name: "Review queue" });
  fireEvent.click(review);
  expect(
    await screen.findByRole("button", { name: "Claim next review" }),
  ).toBeVisible();
  expect(screen.queryByRole("button", { name: "My tasks" })).toBeNull();
  expect(
    screen.queryByRole("button", { name: "Review finalization plan" }),
  ).toBeNull();
  expect(screen.queryByText("Template configuration")).toBeNull();
  await waitFor(() => {
    expect(production.getProjectWorkbench).toHaveBeenLastCalledWith(
      "project",
      expect.objectContaining({ view: "review" }),
    );
  });
});
it("renders the Chinese personal page", async () => {
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: () => undefined, t: translator("zh") }}
    >
      <LabelingPage params={new URLSearchParams()} />
    </I18nContext.Provider>,
  );
  expect(
    await screen.findByRole("heading", { name: "我的数据" }),
  ).toBeVisible();
  expect(screen.getByLabelText("生产项目")).toBeVisible();
});
it("renders empty and failed reads without inventing project statistics", async () => {
  vi.mocked(production.getWorkbench).mockResolvedValue({
    ...labelingIndex,
    projects: [],
  });
  render(<LabelingPage params={new URLSearchParams()} />);
  expect(await screen.findByText(/No production projects yet/)).toBeVisible();
});
it("shows the personal project's locked template version beside an upgrade", async () => {
  const template = labelingProject.template;
  if (!template) throw new Error("fixture template");
  vi.mocked(production.getProjectWorkbench).mockResolvedValue({
    ...labelingProject,
    latest_template: { ...template, revision: template.revision + 1 },
  });
  render(<LabelingPage params={new URLSearchParams()} />);
  expect(
    await screen.findByText(
      `Current template v${String(template.revision)}, latest v${String(template.revision + 1)}`,
    ),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "Prepare upgrade" })).toBeVisible();
});
