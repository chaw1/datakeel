import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { unmeasuredIoU } from "../../../test/labelingFixtures";

import {
  clearWorkspaceSnapshot,
  readWorkspaceSnapshot,
  writeWorkspaceSnapshot,
} from "./workspaceSnapshot";

import type { WorkspaceSnapshot } from "./workspaceSnapshot";

function workspace(actor = "person-1"): WorkspaceSnapshot {
  const scopes = { actor, scopes: ["production:annotate"], zero_users: false };
  const project = {
    id: "project-1",
    name: "Generated test project",
    dataset_id: "dataset-1",
    version_id: "version-1",
    label_set_id: "labels-1",
    label_set_version: 1,
    guidelines: "",
    review_prompt_shown: false,
    workflow_tier: "group" as const,
    lease_minutes: 10,
    dispatch_strategy: "claim" as const,
    review_sample_rate: 1,
    created_at: "2026-10-30T00:00:00Z",
  };
  const task = {
    id: "task-1",
    project_id: project.id,
    package_id: "package-1",
    sample_id: "sample-1",
    priority: 0,
    round: 0,
    state: "in_progress" as const,
  };
  return {
    index: {
      actor,
      projects: [project],
      effective_scopes: scopes,
      zero_users: false,
    },
    project: {
      project,
      effective_scopes: scopes,
      tasks: [task],
      packages: [],
      label_set: {
        id: "labels-1",
        name: "Generated labels",
        version: 1,
        labels: [],
        affected_annotations: 0,
        affected_revisions: 0,
        migration: [],
        published: true,
        created_at: "2026-10-30T00:00:00Z",
      },
      template: null,
      progress: {
        project_id: project.id,
        counts: [],
        rework_task_ids: [],
        status: "active",
        total: 1,
      },
      workload: { project_id: project.id, annotators: [] },
      confidence: { project_id: project.id, buckets: [], total: 0 },
      prelabel_accuracy: {
        project_id: project.id,
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
      prelabel_spend: [],
      agreement: {
        annotator_count: 0,
        boxes: [],
        spans: [],
        findings: [],
        sample_count: 0,
        classification: {
          pairs: [],
          fleiss_kappa: { value: null, sample_count: 0 },
          krippendorff_alpha: { value: null, sample_count: 0 },
        },
      },
      task_risks: [],
      task_samples: [],
    },
    task: {
      task,
      sample: {
        id: "sample-1",
        name: "Generated sample",
        media_type: "text/plain",
        text: "Sample text",
        content_url: "/api/media/sample-1",
      },
      revisions: [],
      reviews: [],
      assignments: [],
    },
  };
}

beforeEach(() => {
  sessionStorage.clear();
});
afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

it("restores the last verified actor's project and task across a same-tab reload", () => {
  const snapshot = workspace();
  expect(writeWorkspaceSnapshot(snapshot)).toBe(true);
  expect(readWorkspaceSnapshot()).toEqual(snapshot);
  expect(readWorkspaceSnapshot("person-1")).toEqual(snapshot);
  expect(readWorkspaceSnapshot("person-2")).toBeNull();
  expect(localStorage.length).toBe(0);
});

it("rejects scopes from another actor and unrelated project or task snapshots", () => {
  const snapshot = workspace();
  expect(
    writeWorkspaceSnapshot({
      ...snapshot,
      index: { ...snapshot.index, actor: "other" },
    }),
  ).toBe(false);
  if (!snapshot.project || !snapshot.task)
    throw new Error("Missing fixture project/task");
  expect(
    writeWorkspaceSnapshot({
      ...snapshot,
      project: {
        ...snapshot.project,
        effective_scopes: {
          ...snapshot.project.effective_scopes,
          actor: "other",
        },
      },
    }),
  ).toBe(false);
  expect(
    writeWorkspaceSnapshot({
      ...snapshot,
      index: { ...snapshot.index, projects: [] },
    }),
  ).toBe(false);
  expect(
    writeWorkspaceSnapshot({
      ...snapshot,
      task: {
        ...snapshot.task,
        task: { ...snapshot.task.task, project_id: "another-project" },
      },
    }),
  ).toBe(false);
  expect(
    writeWorkspaceSnapshot({
      ...snapshot,
      task: {
        ...snapshot.task,
        sample: { ...snapshot.task.sample, id: "another-sample" },
      },
    }),
  ).toBe(false);
  expect(writeWorkspaceSnapshot({ ...snapshot, project: null })).toBe(false);
  expect(readWorkspaceSnapshot()).toBeNull();
});

it("drops a project snapshot saved before accuracy and spend facts existed", () => {
  const snapshot = workspace();
  if (!snapshot.project) throw new Error("Missing fixture project");
  const withoutSpend: Record<string, unknown> = { ...snapshot.project };
  delete withoutSpend.prelabel_spend;
  const exactOnly: Record<string, unknown> = {
    ...snapshot.project.prelabel_accuracy,
  };
  delete exactOnly.iou_50;
  for (const project of [
    withoutSpend,
    { ...snapshot.project, prelabel_accuracy: exactOnly },
  ])
    expect(
      writeWorkspaceSnapshot({
        ...snapshot,
        project: project as typeof snapshot.project,
      }),
    ).toBe(false);
});

it("clears the prior actor's tab snapshot when the server verifies a different actor", () => {
  writeWorkspaceSnapshot(workspace("person-1"));
  writeWorkspaceSnapshot(workspace("person-2"));
  expect(readWorkspaceSnapshot()?.index.actor).toBe("person-2");
  expect(
    sessionStorage.getItem("datakeel.labeling.workspace:person-1"),
  ).toBeNull();
  expect(clearWorkspaceSnapshot()).toBe(true);
  expect(readWorkspaceSnapshot()).toBeNull();
});

it("supports an index-only snapshot and does not restore arbitrary localStorage data", () => {
  const snapshot = { ...workspace(), project: null, task: null };
  writeWorkspaceSnapshot(snapshot);
  expect(readWorkspaceSnapshot()).toEqual(snapshot);
  const encoded =
    sessionStorage.getItem("datakeel.labeling.workspace:person-1") ?? "";
  localStorage.setItem("datakeel.labeling.workspace:person-1", encoded);
  localStorage.setItem("datakeel.labeling.workspace-actor", "person-1");
  sessionStorage.clear();
  expect(readWorkspaceSnapshot()).toBeNull();
});

it.each(["{broken", '{"version":2}', '{"version":1,"value":null}'])(
  "ignores an invalid stored envelope %s",
  (stored) => {
    writeWorkspaceSnapshot(workspace());
    sessionStorage.setItem("datakeel.labeling.workspace:person-1", stored);
    expect(readWorkspaceSnapshot()).toBeNull();
  },
);

it("returns safe failures if browser storage is blocked or full", () => {
  const read = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new DOMException("Storage blocked");
  });
  expect(readWorkspaceSnapshot()).toBeNull();
  expect(writeWorkspaceSnapshot(workspace())).toBe(false);
  expect(clearWorkspaceSnapshot()).toBe(false);
  read.mockRestore();
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("Storage full");
  });
  expect(writeWorkspaceSnapshot(workspace())).toBe(false);
  expect(readWorkspaceSnapshot()).toBeNull();
});
