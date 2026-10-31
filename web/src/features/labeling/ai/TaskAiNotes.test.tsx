import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as production from "../../../api/production";
import { I18nContext, translator } from "../../../i18n/context";
import { draft, human, project, task } from "../../../test/taskAiFixtures";
import * as actions from "../actions";
import { defaultTemplate } from "../model";
import { TaskSession } from "../TaskSession";

import type {
  AnnotationRecord,
  ProjectWorkbench,
  TaskWorkbench,
} from "../../../api/production";
import type { ActionRun } from "../../../api/types";
import type { Locale } from "../../../i18n/context";

vi.mock("../../../api/production", () => ({
  getTaskWorkbench: vi.fn(),
  getTaskStatus: vi.fn(() => new Promise(() => undefined)),
}));
vi.mock("../actions", () => ({
  mutateProduction: vi.fn(),
  actionDetails: vi.fn(),
}));
// The editor only reports how many boxes it was given.
vi.mock("../editors/AnnotationEditor", () => ({
  AnnotationEditor: ({ value }: { value: AnnotationRecord }) => (
    <output data-testid="editor">{`${String(value.boxes?.length ?? 0)} boxes`}</output>
  ),
}));

function mount(
  value: TaskWorkbench,
  workbench: ProjectWorkbench,
  locale: Locale = "en",
) {
  render(
    <I18nContext.Provider
      value={{ locale, setLocale: () => undefined, t: translator(locale) }}
    >
      <TaskSession
        task={value}
        project={workbench}
        actor="local"
        canSync
        onNavigate={vi.fn()}
        onChanged={vi.fn()}
        onSnapshot={vi.fn()}
        registerGuard={vi.fn()}
      />
    </I18nContext.Provider>,
  );
}
function submit(name = "Annotation workbench") {
  fireEvent.keyDown(screen.getByRole("region", { name }), {
    key: "Enter",
    ctrlKey: true,
  });
}
function calls() {
  return vi.mocked(actions.mutateProduction).mock.calls;
}

beforeEach(() => {
  vi.mocked(production.getTaskWorkbench).mockReset();
  vi.mocked(actions.mutateProduction)
    .mockReset()
    .mockResolvedValue({ status: "SUCCEEDED" } as ActionRun);
  vi.mocked(actions.actionDetails).mockReset().mockReturnValue(human);
});

it("starts group work over a low-confidence draft empty and loads the draft on request", () => {
  mount(task([draft]), project("group", ["production:annotate"]));
  expect(screen.getByTestId("editor")).toHaveTextContent("0 boxes");
  expect(screen.getByText("Model confidence: low tier")).toBeVisible();
  expect(
    screen.getByText(
      "The model was unsure here, so you start from an empty annotation.",
    ),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Use model draft" }));
  expect(screen.getByTestId("editor")).toHaveTextContent("2 boxes");
  expect(screen.queryByRole("button", { name: "Use model draft" })).toBeNull();
});

it("saves the empty start with an empty list per enabled component, then submits it", async () => {
  vi.mocked(production.getTaskWorkbench).mockResolvedValue(
    task([draft, human]),
  );
  const both = project("group", ["production:annotate"], {
    template: {
      ...defaultTemplate,
      component_config: { components: ["box", "classification"] },
    },
  });
  mount(task([draft]), both);
  submit();
  await waitFor(() => {
    expect(actions.mutateProduction).toHaveBeenCalledWith("submit_task", {
      task_id: "task-1",
    });
  });
  const [save] = calls();
  expect(save[0]).toBe("save_revision");
  expect(save[1]).toMatchObject({ previous_revision_id: "draft" });
  expect(save[1].annotation).toMatchObject({
    sample_id: "sample-1",
    annotator_id: "local",
    boxes: [],
    labels: [],
  });
  expect(save[1].annotation).not.toHaveProperty("polygons");
  expect(save[1].annotation).not.toHaveProperty("spans");
});

it("keeps the draft in personal projects and only shows its tier", () => {
  mount(task([draft]), project("personal", ["production:annotate"]));
  expect(screen.getByTestId("editor")).toHaveTextContent("2 boxes");
  expect(screen.getByText("Model confidence: low tier")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Use model draft" })).toBeNull();
});

it.each([
  ["a medium draft in group work", "group", "medium"],
  ["a draft in a personal project", "personal", "low"],
] as const)(
  "confirms %s as the person's own revision before submitting it untouched",
  async (_case, tier, confidence) => {
    vi.mocked(production.getTaskWorkbench).mockResolvedValue(
      task([draft, human]),
    );
    const shown = { ...draft, confidence_tier: confidence };
    mount(task([shown]), project(tier, ["production:annotate"]));
    expect(screen.getByTestId("editor")).toHaveTextContent("2 boxes");
    submit();
    await waitFor(() => {
      expect(calls().map(([name]) => name)).toEqual([
        "save_revision",
        "submit_task",
      ]);
    });
    expect(calls()[0][1]).toMatchObject({
      previous_revision_id: "draft",
      annotation: { annotator_id: "local", boxes: draft.annotation.boxes },
    });
  },
);

it("explains a template minimum in the interface language instead of sending an empty start", async () => {
  const minimum = project("group", ["production:annotate"], {
    template: {
      ...defaultTemplate,
      validation_rules: { min_annotations: 1 },
    },
  });
  mount(task([draft]), minimum, "zh");
  submit("标注工作台");
  expect(
    await screen.findByText("还不能提交：至少需要 1 个标注（现在 0 个）"),
  ).toBeVisible();
  expect(actions.mutateProduction).not.toHaveBeenCalled();
});

it("says a high draft is kept for a person while too few reviewed samples exist", () => {
  const high = task([{ ...draft, confidence_tier: "high" }]);
  mount(
    high,
    project("group", ["production:annotate"], {
      confidence_thresholds: {
        high: 0.85,
        low: 0.5,
        source: "default",
        objects: 12,
        minimum_objects: 30,
        notes: ["insufficient_samples"],
        tiers: [],
        segments: [],
        pass_through: false,
      },
    }),
  );
  expect(screen.getByText("Model confidence: high tier")).toBeVisible();
  expect(
    screen.getByText(
      "Not enough reviewed samples yet: high-confidence drafts are not passed straight to review",
    ),
  ).toBeVisible();
});
