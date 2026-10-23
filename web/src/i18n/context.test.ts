import { expect, it } from "vitest";

import { translator } from "./context";
import { en } from "./en";
import { localizedCatalogName } from "./graphCatalogNames";
import { zh } from "./zh";

import type { MessageKey } from "./en";

const countedMessages: [MessageKey, string, string][] = [
  ["approvalImpactSummary", "1 object · 1 KB", "2 objects · 1 KB"],
  [
    "qualityAlerts",
    "Quality alerts · 1 dataset",
    "Quality alerts · 2 datasets",
  ],
  ["evTitle", "Evidence · 1 sample", "Evidence · 2 samples"],
  ["evCandidates", "1 candidate to review", "2 candidates to review"],
  ["evResultCount", "1 matching sample", "2 matching samples"],
  [
    "evMoreAssertions",
    "1 more assertion in details",
    "2 more assertions in details",
  ],
  ["objCount", "1 record", "2 records"],
  ["rejectedPlans", "Rejected 1 plan.", "Rejected 2 plans."],
  ["graphConnections", "1 link", "2 links"],
  ["graphAssetCount", "1 asset", "2 assets"],
  ["graphEdgeCount", "1 edge", "2 edges"],
  ["graphGroupMembers", "Run · 1 run", "Run · 2 runs"],
  [
    "graphKnownNeighbors",
    "Showing 1 neighbor from this layer",
    "Showing 2 neighbors from this layer",
  ],
  ["tokenBudget", "1 token", "2 tokens"],
  ["files", "file", "files"],
  ["shards", "shard", "shards"],
  ["snapshots", "snapshot", "snapshots"],
  ["dataModalities", "data modality", "data modalities"],
];

it.each(countedMessages)("pluralizes %s using its count", (key, one, other) => {
  const t = translator("en");
  expect(t(key, { count: 1, name: "Run", size: "1 KB" })).toBe(one);
  expect(t(key, { count: 2, name: "Run", size: "1 KB" })).toBe(other);
});

it("pluralizes independent file and version counts without changing Chinese", () => {
  expect(
    translator("en")("datasetSummary", {
      files: 1,
      versions: 2,
      modalities: "image",
    }),
  ).toBe("1 file · image · 2 versions");
  expect(
    translator("en")("datasetSummary", {
      files: 2,
      versions: 1,
      modalities: "image",
    }),
  ).toBe("2 files · image · 1 version");
  expect(translator("en")("files", { count: 0 })).toBe("files");
  expect(translator("en")("files", { count: 1.5 })).toBe("files");
  expect(translator("zh")("evCandidates", { count: 1 })).toBe("1 条候选待审");
});

it("renders every plural template without leaving formatting syntax", () => {
  for (const key of Object.keys(en) as MessageKey[]) {
    for (const count of [0, 1, 2]) {
      expect(
        translator("en")(key, { count, files: count, versions: count }),
      ).not.toContain(", plural,");
    }
  }
});

it("removes untranslated UI words while retaining technical identifiers", () => {
  const visibleCopy = Object.values(zh)
    .join("\n")
    .replaceAll("caption.txt", "");
  expect(visibleCopy).not.toMatch(
    /\b(?:task|Pipeline run|Caption|Agent|Trace|manifest|token)\b/i,
  );
  expect(zh.graphTask).toBe("任务");
  expect(zh.graphPipelineRun).toBe("流水线运行");
  expect(zh.askReference).toContain("UTC");
  expect(zh.evPairedLayout).toContain("caption.txt");
});

it("switches built-in metric and dimension names while preserving custom names", () => {
  expect(localizedCatalogName("零售额", translator("en"))).toBe(
    "Retail revenue",
  );
  expect(localizedCatalogName("Retail revenue", translator("zh"))).toBe(
    "零售额",
  );
  expect(localizedCatalogName("零售区域", translator("en"))).toBe(
    "Retail region",
  );
  expect(localizedCatalogName("Custom metric", translator("zh"))).toBe(
    "Custom metric",
  );
});
