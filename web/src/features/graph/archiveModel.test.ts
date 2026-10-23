import { expect, it } from "vitest";

import { graph } from "../../test/fixtures";

import {
  aggregateInfo,
  archiveName,
  archiveProjection,
  safeNodeName,
} from "./archiveModel";

import type { GraphNode } from "../../api/types";

function node(id: string, name: string, kind = "file"): GraphNode {
  return {
    id,
    asset_id: id,
    asset_type: kind,
    namespace: "default",
    label: name,
    display_name: name,
  };
}

it("uses the last two display-name segments and abbreviates through the middle", () => {
  const item = node(
    "id",
    "workspace/train/scene-0817/a-very-long-camera-image-name.png",
  );
  item.label = "Old label";
  const name = archiveName(item);
  expect(name.prefix).toBe("scene-0817/");
  expect(name.name).toContain("…");
  expect(name.name).toMatch(/image-name\.png$/);
  expect(name.name).not.toContain("Old");
  const unnamed = node(
    "dce31df1-f876-4cc8-aedd-b92d9f248975",
    "dce31df1-f876-4cc8-aedd-b92d9f248975",
  );
  expect(safeNodeName(unnamed)).toBe("File dce31df1");
});

it("merges only action runs sharing a display name and retains the focused member", () => {
  const nodes = [
    node("run-a", "decide_assertions", "action_run"),
    node("run-b", "decide_assertions", "action_run"),
    node("file-a", "decide_assertions"),
    node("file-b", "decide_assertions"),
  ];
  const result = archiveProjection({ ...graph, nodes, edges: [] }, "run-b");
  expect(result.groups).toHaveLength(3);
  expect(result.groups[0].node.id).toBe("run-b");
  expect(result.groups[0].members.map((member) => member.id)).toEqual([
    "run-a",
    "run-b",
  ]);
});

it("collapses excess neighbors by edge kind and preserves their backing records", () => {
  const nodes = Array.from({ length: 75 }, (_, index) =>
    node(`file-${String(index)}`, `file-${String(index)}.png`),
  );
  const edges = nodes.slice(1).map((target, index) => ({
    ...graph.edges[0],
    source: nodes[0].id,
    target: target.id,
    kind: (["lineage", "semantic", "catalog"] as const)[index % 3],
  }));
  const result = archiveProjection({ ...graph, nodes, edges }, "file-34");
  expect(result.groups.length).toBeLessThanOrEqual(25);
  expect(result.graph.nodes.some((item) => item.id === "file-34")).toBe(true);
  expect(
    result.groups.filter((group) => aggregateInfo(group.node)),
  ).toHaveLength(3);
  expect(result.groups.flatMap((group) => group.members)).toHaveLength(75);
  expect(
    result.graph.edges.every(
      (edge) =>
        result.graph.nodes.some((item) => item.id === edge.source) &&
        result.graph.nodes.some((item) => item.id === edge.target),
    ),
  ).toBe(true);
  expect(result.graph.events).toEqual(graph.events);
});

it("counts repeated action runs as one before deciding whether to collapse", () => {
  const nodes = Array.from({ length: 30 }, (_, index) =>
    node(`run-${String(index)}`, "decide_assertions", "action_run"),
  );
  const result = archiveProjection({ ...graph, nodes, edges: [] });
  expect(result.groups).toHaveLength(1);
  expect(result.groups[0].members).toHaveLength(30);
  expect(result.graph.truncated).toBe(false);
});

it("uses readable types for opaque hashes without hiding filenames containing hashes", () => {
  for (const length of [32, 40, 64, 128]) {
    const hash = "abcdef0123456789".repeat(8).slice(0, length);
    expect(safeNodeName(node(hash, hash, "knowledge_bundle"))).toBe(
      "Knowledge bundle abcdef01",
    );
    expect(safeNodeName(node(hash, `scene/${hash}.png`))).toBe(
      `scene/${hash}.png`,
    );
    expect(safeNodeName(node(hash, `frame-${hash}.jpg`))).toBe(
      `frame-${hash}.jpg`,
    );
  }
  const opaque = "01JQZPKVCAYF4EKWQVMTXR8HWG";
  expect(safeNodeName(node(opaque, opaque, "action_run"))).toBe(
    "Action run 01JQZPKV",
  );
});

it("distinguishes filenames and table fields with muted prefixes", () => {
  expect(archiveName(node("file-id", "val/scene-0817/image.png"))).toEqual({
    prefix: "scene-0817/",
    name: "image.png",
  });
  expect(archiveName(node("orders-date", "orders.date", "column"))).toEqual({
    prefix: "orders.",
    name: "date",
  });
  expect(archiveName(node("sales-date", "sales.date", "column"))).toEqual({
    prefix: "sales.",
    name: "date",
  });
  expect(safeNodeName(node("shop/main/orders/date", "date", "column"))).toBe(
    "orders.date",
  );
});

it("localizes metric, dimension, task and version names while preserving user names", () => {
  const metric = node("retail_revenue", "零售额", "metric");
  expect(safeNodeName(metric, "zh")).toBe("零售额");
  expect(safeNodeName(metric, "en")).toBe("Retail revenue");
  expect(
    safeNodeName(node("retail_region", "零售区域", "dimension"), "en"),
  ).toBe("Retail region");
  expect(
    safeNodeName(node("custom", "My customized metric", "metric"), "zh"),
  ).toBe("My customized metric");
  expect(safeNodeName(node("run", "Pipeline run", "task"), "zh")).toBe(
    "流水线运行",
  );
  const version = {
    ...node("version-id", "2 · 2026-10-23 12:00 UTC", "version"),
    version: "version-id",
  };
  expect(safeNodeName(version, "zh")).toBe("版本 2 · 2026-10-23 12:00 UTC");
  expect(safeNodeName(version, "en")).toBe("Version 2 · 2026-10-23 12:00 UTC");
  expect(archiveName(version, "zh").name).toBe("版本 2 · 2026-10-23 12:00 UTC");
});

it("removes term prefixes and never leaves unnamed cards showing only the type", () => {
  expect(
    safeNodeName(node("term/零售区域", "term/零售区域", "term"), "zh"),
  ).toBe("零售区域");
  expect(
    safeNodeName(node("dce31df1-f876-4cc8-aedd-b92d9f248975", "file"), "zh"),
  ).toBe("文件 dce31df1");
  expect(
    safeNodeName(node("dce31df1-f876-4cc8-aedd-b92d9f248975", ""), "en"),
  ).toBe("File dce31df1");
  expect(
    safeNodeName(node("dce31df1-f876-4cc8-aedd-b92d9f248975", "File"), "en"),
  ).toBe("File dce31df1");
  expect(
    safeNodeName(node("dce31df1-f876-4cc8-aedd-b92d9f248975", "文件"), "zh"),
  ).toBe("文件 dce31df1");
});

it("uses each asset identity for unnamed versioned files and metric revisions", () => {
  expect(
    safeNodeName({
      ...node("file-123456", "", "file"),
      version: "shared-version",
    }),
  ).toBe("File file-123");
  expect(
    safeNodeName({
      ...node("file-abcdef", "", "file"),
      version: "shared-version",
    }),
  ).toBe("File file-abc");
  expect(
    safeNodeName({ ...node("metric-abcdef", "", "metric"), version: "1" }),
  ).toBe("Metric metric-a");
  expect(
    safeNodeName(
      {
        ...node("dataset-id", "Paired scenes", "dataset"),
        version: "version-id",
      },
      "zh",
    ),
  ).toBe("Paired scenes");
  expect(
    safeNodeName(node("bundle-123456", "", "knowledge_bundle"), "zh"),
  ).toBe("证据包 bundle-1");
  expect(safeNodeName(node("question-123456", "", "question"), "zh")).toBe(
    "问题 question",
  );
  expect(
    archiveName({
      ...node(
        "file-id",
        "scene-0817/very-long-image-file-name-to-abbreviate.png",
      ),
      version: "shared-version",
    }).name,
  ).toContain("…");
});
