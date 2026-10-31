import type { components } from "../api/generated";
import type {
  ProjectWorkbench,
  TaskWorkbench,
  WorkbenchIndex,
} from "../api/production";

/** Object-level accuracy at one IoU threshold with nothing assessed yet. */
export function unmeasuredIoU(
  threshold: number,
): components["schemas"]["IoUAccuracy"] {
  return {
    threshold,
    model_objects: 0,
    human_objects: 0,
    true_positives: 0,
    precision: null,
    recall: null,
    f1: null,
    all_hit_tasks: 0,
    all_hit_rate: null,
  };
}

export const labelingProject: ProjectWorkbench = {
  project: {
    id: "project",
    name: "Generated boxes",
    dataset_id: "dataset",
    version_id: "version",
    label_set_id: "labels",
    label_set_version: 1,
    workflow_tier: "personal",
    guidelines: "",
    review_prompt_shown: false,
    lease_minutes: 10,
    dispatch_strategy: "claim",
    review_sample_rate: 1,
    created_at: "2026-10-30T00:00:00Z",
  },
  packages: [
    {
      id: "package",
      project_id: "project",
      name: "Batch one",
      task_count: 2,
      split_rule: "count",
      created_at: "2026-10-30T00:00:00Z",
    },
  ],
  label_set: {
    id: "labels",
    version: 1,
    name: "Objects",
    labels: [{ id: "cat", name: "Cat", attributes: {} }],
    published: true,
    affected_annotations: 0,
    affected_revisions: 0,
    migration: [],
    created_at: "2026-10-30T00:00:00Z",
  },
  template: {
    id: "template",
    name: "Boxes",
    annotation_type: "box",
    component_config: {},
    revision: 1,
    archived: false,
    attributes: [],
  },
  effective_scopes: { actor: "local", scopes: ["*"], zero_users: true },
  progress: {
    project_id: "project",
    total: 2,
    status: "pending",
    counts: [{ state: "pending", count: 2 }],
    rework_task_ids: [],
  },
  workload: { project_id: "project", annotators: [] },
  confidence: { project_id: "project", total: 0, buckets: [] },
  agreement: {
    classification: {
      pairs: [],
      fleiss_kappa: { value: null, sample_count: 0 },
      krippendorff_alpha: { value: null, sample_count: 0 },
    },
    boxes: [],
    spans: [],
    findings: [],
    sample_count: 0,
    annotator_count: 0,
  },
  tasks: [
    {
      id: "task-1",
      project_id: "project",
      package_id: "package",
      sample_id: "sample-1",
      state: "pending",
      round: 0,
      priority: 0,
    },
    {
      id: "task-2",
      project_id: "project",
      package_id: "package",
      sample_id: "sample-2",
      state: "pending",
      round: 0,
      priority: 0,
    },
  ],
  task_risks: [],
  task_samples: [
    {
      task_id: "task-1",
      sample_id: "sample-1",
      name: "harbor-001.png",
      path: "harbor/day/harbor-001.png",
    },
    {
      task_id: "task-2",
      sample_id: "sample-2",
      name: "harbor-002.png",
      path: "harbor/day/harbor-002.png",
    },
  ],
  prelabel_accuracy: {
    project_id: "project",
    assessed_tasks: 0,
    exact_match_tasks: 0,
    exact_match_rate: null,
    iou_50: unmeasuredIoU(0.5),
    iou_75: unmeasuredIoU(0.75),
    attribute_agreement: {
      matched_objects: 0,
      consistent_objects: 0,
      rate: null,
    },
  },
  confidence_thresholds: null,
  prelabel_spend: [],
  prelabel_progress: [],
};
export const labelingIndex: WorkbenchIndex = {
  actor: "local",
  zero_users: true,
  effective_scopes: labelingProject.effective_scopes,
  projects: [labelingProject.project],
};
export const labelingTask: TaskWorkbench = {
  task: labelingProject.tasks[0],
  sample: {
    id: "sample-1",
    name: "Generated image",
    path: "Generated image",
    media_type: "image/png",
    image_width: 2000,
    image_height: 1500,
    content_url: "/api/production/tasks/task-1/content",
  },
  revisions: [],
  reviews: [],
  assignments: [],
};
