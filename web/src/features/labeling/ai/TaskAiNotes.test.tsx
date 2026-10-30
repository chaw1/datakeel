import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as production from "../../../api/production";
import { labelingProject, labelingTask } from "../../../test/labelingFixtures";
import * as actions from "../actions";
import { TaskSession } from "../TaskSession";

import type { components } from "../../../api/generated";
import type {
  AnnotationRecord,
  ProjectWorkbench,
  TaskWorkbench,
} from "../../../api/production";
import type { ActionRun } from "../../../api/types";
import type { LocateRequest } from "../editors/types";

vi.mock("../../../api/production", () => ({
  getTaskWorkbench: vi.fn(),
  getTaskStatus: vi.fn(() => new Promise(() => undefined)),
}));
vi.mock("../actions", () => ({
  mutateProduction: vi.fn(),
  actionDetails: vi.fn(),
}));
// The editor only reports what it was given, including which object it was asked to select.
vi.mock("../editors/AnnotationEditor", () => {
  function MockEditor({
    value,
    locate: located,
  }: {
    value: AnnotationRecord;
    locate?: LocateRequest | null;
  }) {
    return (
      <output data-testid="editor">
        {`${String(value.boxes?.length ?? 0)} boxes`}
        {located ? ` · ${located.kind} ${String(located.index)}` : ""}
      </output>
    );
  }
  return { AnnotationEditor: MockEditor };
});

type Revision = components["schemas"]["AnnotationRevision"];
type AIReview = components["schemas"]["AIReview"];

const created = "2026-10-30T00:00:00Z";
const draft: Revision = {
  id: "draft",
  task_id: "task-1",
  actor: "prelabel",
  source: "model",
  previous_revision_id: null,
  created_at: created,
  model_name: "qwen-vl",
  model_version: "2026-10",
  confidence: 0.3,
  object_confidences: [0.3, 0.2],
  confidence_tier: "low",
  annotation: {
    sample_id: "sample-1",
    annotator_id: "qwen-vl",
    image_width: 2000,
    image_height: 1500,
    boxes: [
      { category: "cat", x1: 1, y1: 1, x2: 20, y2: 20 },
      { category: "cat", x1: 30, y1: 30, x2: 60, y2: 60 },
    ],
  },
};
const human: Revision = {
  id: "human-1",
  task_id: "task-1",
  actor: "local",
  source: "human",
  previous_revision_id: "draft",
  created_at: created,
  object_confidences: [],
  annotation: { sample_id: "sample-1", annotator_id: "local" },
};
const holding = {
  id: "assignment-1",
  task_id: "task-1",
  actor: "local",
  stage: "annotation" as const,
  active: true,
  created_at: created,
  lease_expires_at: "2026-10-30T00:10:00Z",
};

function project(
  tier: ProjectWorkbench["project"]["workflow_tier"],
  scopes: string[],
): ProjectWorkbench {
  return {
    ...labelingProject,
    project: { ...labelingProject.project, workflow_tier: tier },
    effective_scopes: { actor: "local", zero_users: false, scopes },
  };
}
function task(
  revisions: Revision[],
  state: TaskWorkbench["task"]["state"] = "in_progress",
  aiReview: AIReview | null = null,
): TaskWorkbench {
  return {
    ...labelingTask,
    task: {
      ...labelingTask.task,
      state,
      latest_revision_id: revisions.at(-1)?.id ?? null,
    },
    revisions,
    assignments: state === "in_progress" ? [holding] : [],
    ai_review: aiReview,
  };
}
function review(overrides: Partial<AIReview> = {}): AIReview {
  return {
    id: "ai-review-1",
    project_id: "project",
    task_id: "task-1",
    revision_id: "human-1",
    round: 0,
    risk: 0.62,
    high_risk: true,
    sample_rate: 0.5,
    draw: 0.8,
    decision: "review",
    note: "",
    created_at: created,
    reasons: [
      {
        code: "draft_disagreement",
        message: "Differs from the model draft",
        weight: 0.4,
        evidence: ["Box 2 has IoU 0.31 with the nearest draft box"],
        objects: [
          { kind: "box", index: 1 },
          { kind: "label_set", index: 0 },
        ],
      },
    ],
    ...overrides,
  };
}
function mount(
  value: TaskWorkbench,
  workbench: ProjectWorkbench,
  actor = "local",
) {
  render(
    <TaskSession
      task={value}
      project={workbench}
      actor={actor}
      canSync
      onNavigate={vi.fn()}
      onChanged={vi.fn()}
      onSnapshot={vi.fn()}
      registerGuard={vi.fn()}
    />,
  );
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

it("submits the empty start the person saw, never the hidden low draft", async () => {
  vi.mocked(production.getTaskWorkbench).mockResolvedValue(
    task([draft, human]),
  );
  mount(task([draft]), project("group", ["production:annotate"]));
  fireEvent.keyDown(
    screen.getByRole("region", { name: "Annotation workbench" }),
    { key: "Enter", ctrlKey: true },
  );
  await waitFor(() => {
    expect(actions.mutateProduction).toHaveBeenCalledWith("submit_task", {
      task_id: "task-1",
    });
  });
  const [save] = vi.mocked(actions.mutateProduction).mock.calls;
  expect(save[0]).toBe("save_revision");
  expect(save[1]).toMatchObject({ previous_revision_id: "draft" });
  expect(save[1].annotation).not.toHaveProperty("boxes");
});

it("keeps the draft in personal projects and only shows its tier", () => {
  mount(task([draft]), project("personal", ["production:annotate"]));
  expect(screen.getByTestId("editor")).toHaveTextContent("2 boxes");
  expect(screen.getByText("Model confidence: low tier")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Use model draft" })).toBeNull();
});

it("shows reviewers the risk, decision and reasons above the controls and locates objects", () => {
  mount(
    task([draft, human], "submitted", review()),
    project("group", ["production:review"]),
    "rev",
  );
  const panel = screen.getByRole("region", { name: "AI pre-review" });
  expect(panel).toHaveTextContent("Risk 62%");
  expect(panel).toHaveTextContent("High risk");
  expect(panel).toHaveTextContent("Needs a human review");
  expect(panel).toHaveTextContent("Differs from the model draft");
  expect(panel).toHaveTextContent("weight 0.40");
  expect(panel).toHaveTextContent(
    "Box 2 has IoU 0.31 with the nearest draft box",
  );
  expect(panel).toHaveTextContent("labels");
  expect(screen.queryByRole("button", { name: "Locate labels" })).toBeNull();
  const approve = screen.getByRole("button", { name: "Approve revision" });
  expect(
    panel.compareDocumentPosition(approve) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Locate box 2" }));
  expect(screen.getByTestId("editor")).toHaveTextContent("box 1");
});

it("names known rules in the interface language and keeps template details", () => {
  const reasons = [
    {
      code: "duplicate_bbox",
      message: "The same annotator drew two nearly identical boxes",
      weight: 0.5,
      evidence: [],
      objects: [],
    },
    {
      code: "template_violation",
      message: 'Attribute "kind" is required on box 1',
      weight: 0.9,
      evidence: [],
      objects: [],
    },
  ];
  mount(
    task([draft, human], "submitted", review({ reasons })),
    project("group", ["production:review"]),
    "rev",
  );
  const panel = screen.getByRole("region", { name: "AI pre-review" });
  expect(panel).toHaveTextContent("Duplicate box");
  expect(panel).not.toHaveTextContent("nearly identical");
  expect(panel).toHaveTextContent("Breaks the template");
  expect(panel).toHaveTextContent('Attribute "kind" is required on box 1');
});

it("offers no locate buttons when the scored revision is not the one on screen", () => {
  mount(
    task([draft, human], "submitted", review({ revision_id: "older" })),
    project("group", ["production:review"]),
    "rev",
  );
  expect(screen.getByRole("region", { name: "AI pre-review" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "Locate box 2" })).toBeNull();
});

it("tells a personal annotator about a risky submission without blocking anything", () => {
  const scored = task(
    [draft, human],
    "approved",
    review({ decision: "personal", risk: 0.45, high_risk: true }),
  );
  mount(scored, project("personal", ["production:annotate"]));
  const notice = screen.getByRole("status", {
    name: "AI pre-review of your submission",
  });
  expect(notice).toHaveTextContent(
    "Personal project: a hint only, nothing is blocked",
  );
});

it("stays quiet for a low-risk personal submission and for annotators in group work", () => {
  mount(
    task(
      [draft, human],
      "approved",
      review({ decision: "personal", risk: 0.2, high_risk: false }),
    ),
    project("personal", ["production:annotate"]),
  );
  mount(
    task([draft, human], "submitted", review()),
    project("group", ["production:annotate"]),
  );
  expect(screen.queryByText(/AI pre-review/)).toBeNull();
});
