import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../../i18n/context";
import {
  draft,
  human,
  project,
  review,
  task,
} from "../../../test/taskAiFixtures";
import { TaskSession } from "../TaskSession";

import { AIReviewPanel } from "./AIReviewPanel";

import type {
  AnnotationRecord,
  ProjectWorkbench,
  TaskWorkbench,
} from "../../../api/production";
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

it("shows reviewers the risk, decision and plain reasons above the controls and locates objects", () => {
  mount(
    task([draft, human], "submitted", review()),
    project("group", ["production:review"]),
    "rev",
  );
  const panel = screen.getByRole("region", { name: "AI pre-review" });
  expect(panel).toHaveTextContent("Risk 62%");
  expect(panel).toHaveTextContent("High risk");
  expect(panel).toHaveTextContent("Needs a human review");
  expect(panel).toHaveTextContent("Departs from a confident model draft");
  expect(panel).toHaveTextContent(
    "Box 2 barely overlaps the nearest model box.",
  );
  expect(panel).toHaveTextContent("weight 0.40");
  expect(panel).not.toHaveTextContent("iou=0.31");
  expect(panel).not.toHaveTextContent("几乎不重合");
  expect(panel).toHaveTextContent("labels");
  expect(screen.queryByRole("button", { name: "Locate labels" })).toBeNull();
  const approve = screen.getByRole("button", { name: "Approve revision" });
  expect(
    panel.compareDocumentPosition(approve) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Locate box 2" }));
  expect(screen.getByTestId("editor")).toHaveTextContent("box 1");
});

it("names known rules in the interface language, then says what happened", () => {
  const reasons = [
    {
      code: "duplicate_bbox",
      message: "The same annotator drew two nearly identical boxes.",
      message_zh: "",
      weight: 0.5,
      evidence: [],
      objects: [],
    },
    {
      code: "template_violation",
      message: 'Attribute "kind" is required on box 1.',
      message_zh: "",
      weight: 0.9,
      evidence: [],
      objects: [],
    },
    {
      code: "brand_new_rule",
      message: "Something new looked off.",
      message_zh: "",
      weight: 0.1,
      evidence: ["internal-id-42"],
      objects: [],
    },
  ];
  mount(
    task([draft, human], "submitted", review({ reasons })),
    project("group", ["production:review"]),
    "rev",
  );
  const panel = screen.getByRole("region", { name: "AI pre-review" });
  expect(panel).toHaveTextContent(
    "Duplicate box The same annotator drew two nearly identical boxes.",
  );
  expect(panel).toHaveTextContent(
    'Breaks the template Attribute "kind" is required on box 1.',
  );
  expect(screen.getAllByText("Something new looked off.")).toHaveLength(1);
  expect(panel).not.toHaveTextContent("internal-id-42");
});

it("reads the Chinese sentence in Chinese and never shows internal evidence", () => {
  const onLocate = vi.fn();
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: () => undefined, t: translator("zh") }}
    >
      <AIReviewPanel
        review={review({
          reasons: [
            ...review().reasons,
            {
              code: "duplicate_bbox",
              message: "Two boxes are the same.",
              message_zh: "",
              weight: 0.2,
              evidence: ["(0, 1)"],
              objects: [],
            },
          ],
        })}
        onLocate={onLocate}
      />
    </I18nContext.Provider>,
  );
  const panel = screen.getByRole("region", { name: "AI 预审" });
  expect(panel).toHaveTextContent(
    "和高置信模型草稿差别大 框 2 和最近的模型框几乎不重合。",
  );
  expect(panel).not.toHaveTextContent("barely overlaps");
  expect(panel).toHaveTextContent("重复框 Two boxes are the same.");
  expect(panel).not.toHaveTextContent("iou=0.31");
  expect(panel).not.toHaveTextContent("MAD");
  expect(panel).not.toHaveTextContent("(0, 1)");
  fireEvent.click(screen.getByRole("button", { name: "定位框 2" }));
  expect(onLocate).toHaveBeenCalledWith({ kind: "box", index: 1 });
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
