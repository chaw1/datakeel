import { imageFile, version } from "../../test/fixtures";
import { leakage, splitSet } from "../training/testFixtures";

import type { LeakageReport, SplitSet } from "../../api/training";
import type { Version } from "../../api/types";

export const original: Version = {
  ...version,
  file_count: 3,
  manifest: [
    {
      ...imageFile,
      id: "sample-a",
      filename: "train/scene-one.png",
      metadata: { evidence_sample: { annotation: null } },
    },
    { ...imageFile, id: "sample-b", filename: "val/scene-copy.png" },
    { ...imageFile, id: "sample-c", filename: "test/scene-two.png" },
  ],
};
export const corrected: Version = {
  ...original,
  id: "version-2",
  created_at: original.created_at + 1,
  file_count: 2,
  manifest: original.manifest.filter((file) => file.id !== "sample-b"),
};
export const originalSplit: SplitSet = {
  ...splitSet,
  request: {
    ...splitSet.request,
    name: "Delivery review",
    source: "directory",
  },
};
export const correctedSplit: SplitSet = {
  ...originalSplit,
  id: "split-2",
  version_id: corrected.id,
  members: originalSplit.members.filter(
    (member) => member.sample_id !== "sample-b",
  ),
  distributions: originalSplit.distributions.filter(
    (item) => item.split !== "val",
  ),
};
export const matched: LeakageReport = {
  ...leakage,
  pairs: leakage.pairs.slice(0, 2),
};
export const clean: LeakageReport = {
  ...matched,
  version_id: corrected.id,
  split_set_id: correctedSplit.id,
  sample_count: 2,
  pairs: [],
};
