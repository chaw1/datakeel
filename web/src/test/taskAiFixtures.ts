import { labelingProject, labelingTask } from "./labelingFixtures";

import type { components } from "../api/generated";
import type { ProjectWorkbench, TaskWorkbench } from "../api/production";

type Revision = components["schemas"]["AnnotationRevision"];
type AIReview = components["schemas"]["AIReview"];

const created = "2026-10-30T00:00:00Z";
/** A low-confidence model draft with two boxes; tests spread it to change the tier. */
export const draft: Revision = {
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
export const human: Revision = {
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

export function project(
  tier: ProjectWorkbench["project"]["workflow_tier"],
  scopes: string[],
  overrides: Partial<ProjectWorkbench> = {},
): ProjectWorkbench {
  return {
    ...labelingProject,
    project: { ...labelingProject.project, workflow_tier: tier },
    effective_scopes: { actor: "local", zero_users: false, scopes },
    ...overrides,
  };
}
export function task(
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
export function review(overrides: Partial<AIReview> = {}): AIReview {
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
        code: "prelabel_disagreement",
        message: "Box 2 barely overlaps the nearest model box.",
        message_zh: "框 2 和最近的模型框几乎不重合。",
        weight: 0.4,
        evidence: ["box[1] iou=0.31 vs draft#0 (MAD 2.4)"],
        objects: [
          { kind: "box", index: 1 },
          { kind: "label_set", index: 0 },
        ],
      },
    ],
    ...overrides,
  };
}
