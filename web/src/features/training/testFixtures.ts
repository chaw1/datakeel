import type { LeakageReport, SplitSet } from "../../api/training";

export const splitSet: SplitSet = {
  id: "split-1",
  dataset_id: "dataset-1",
  version_id: "version-1",
  request: {
    name: "baseline",
    ratios: { train: 0.8, val: 0.1, test: 0.1 },
    seed: 42,
    stratify: true,
    group_field: "batch",
    avoid_leakage: true,
    image_threshold: 8,
    text_threshold: 3,
    source: "generated",
  },
  members: [
    {
      sample_id: "sample-a",
      split: "train",
      labels: ["harbor"],
      annotations: [],
      sha256: "a".repeat(64),
    },
    {
      sample_id: "sample-b",
      split: "val",
      labels: ["bridge"],
      annotations: [],
      sha256: "b".repeat(64),
    },
    {
      sample_id: "sample-c",
      split: "test",
      labels: ["harbor"],
      annotations: [],
      sha256: "c".repeat(64),
    },
  ],
  distributions: [
    { split: "train", count: 1, labels: [{ label: "harbor", count: 1 }] },
    { split: "val", count: 1, labels: [{ label: "bridge", count: 1 }] },
    { split: "test", count: 1, labels: [{ label: "harbor", count: 1 }] },
  ],
  created_at: "2026-10-29T00:00:00Z",
  algorithm_version: "1.3-iterative-text",
};

export const leakage: LeakageReport = {
  split_set_id: splitSet.id,
  dataset_id: splitSet.dataset_id,
  version_id: splitSet.version_id,
  sample_count: 3,
  checked_signals: ["exact", "image", "text", "group"],
  pairs: ["exact", "image", "text", "group"].map((kind) => ({
    kind: kind as LeakageReport["pairs"][number]["kind"],
    left_id: "sample-a",
    right_id: "sample-b",
    left_split: "train",
    right_split: "val",
    distance: kind === "image" ? 2 : 0,
    detail: `${kind} evidence`,
  })),
};
