import { expect, it, vi } from "vitest";

import { objectData, mockObjects } from "../features/object/testFixtures";
import { dataset, file, version } from "../test/fixtures";

import { loadObject, objectGraphPath } from "./objects";

it("resolves a direct file identity using search and preserves immutable version context", async () => {
  const fetch = mockObjects();
  const value = await loadObject({ kind: "file", id: file.id });
  expect(value.target).toMatchObject({
    datasetId: dataset.id,
    versionId: version.id,
  });
  expect(value.file?.filename).toBe("processed.txt");
  expect(fetch.mock.calls.some(([url]) => url.startsWith("/api/search?"))).toBe(
    true,
  );
});
it("uses both catalog and semantic overlays with bounded graph expansion", () => {
  const target = { kind: "table", id: "source/main/orders" } as const;
  const query = new URL(objectGraphPath(target), "http://localhost")
    .searchParams;
  expect(Object.fromEntries(query)).toMatchObject({
    asset_id: target.id,
    hops: "2",
    max_nodes: "25",
    include_catalog: "true",
    include_semantic: "true",
    collapse: "true",
  });
  expect(
    new URL(objectGraphPath(target, true), "http://localhost").searchParams.get(
      "collapse",
    ),
  ).toBe("false");
});
it("follows evidence cursors instead of reporting only the first page as the full count", async () => {
  const base = mockObjects();
  let page = 0;
  vi.stubGlobal("fetch", (path: string, init?: RequestInit) => {
    if (path === "/api/evidence/query") {
      page++;
      return Promise.resolve(
        new Response(
          JSON.stringify({
            items: objectData.samples,
            total: 2,
            next_cursor: page === 1 ? "next" : null,
            truncated: false,
          }),
        ),
      );
    }
    return base(path, init);
  });
  const value = await loadObject({ kind: "dataset", id: dataset.id });
  expect(value.samples).toHaveLength(2);
  expect(page).toBe(2);
});
it("rejects a file outside its declared dataset instead of showing another file", async () => {
  mockObjects();
  await expect(
    loadObject({ kind: "file", id: "missing", datasetId: dataset.id }),
  ).rejects.toThrow("File not found");
});

it("reads removed files from immutable manifests and overlays their current graph status", async () => {
  const base = mockObjects();
  vi.stubGlobal("fetch", (path: string, init?: RequestInit) => {
    if (path.endsWith("/files")) return Promise.resolve(new Response("[]"));
    if (path.startsWith("/api/lineage/graph?"))
      return Promise.resolve(
        new Response(
          JSON.stringify({
            ...objectData.graph,
            nodes: [
              {
                id: file.id,
                asset_id: file.id,
                namespace: "default",
                asset_type: "file",
                label: file.filename,
                deleted: true,
              },
            ],
          }),
        ),
      );
    return base(path, init);
  });
  const value = await loadObject({
    kind: "file",
    id: file.id,
    datasetId: dataset.id,
  });
  expect(value.file?.id).toBe(file.id);
  expect(value.file?.metadata?.deleted).toBe(true);
});
it("queries a version's dataset lineage because versions are pinned dataset snapshots", () => {
  const query = new URL(
    objectGraphPath({ kind: "version", id: version.id, datasetId: dataset.id }),
    "http://localhost",
  ).searchParams;
  expect(query.get("asset_id")).toBe(dataset.id);
});

it("excludes removed candidates from dataset facts while preserving file evidence", async () => {
  const base = mockObjects();
  vi.stubGlobal("fetch", (path: string, init?: RequestInit) => {
    if (path === "/api/evidence/query") {
      const request = JSON.parse(
        typeof init?.body === "string" ? init.body : "{}",
      ) as { include_deleted: boolean };
      const items = request.include_deleted ? objectData.samples : [];
      return Promise.resolve(
        new Response(
          JSON.stringify({
            items,
            total: items.length,
            next_cursor: null,
            truncated: false,
          }),
        ),
      );
    }
    return base(path, init);
  });
  const current = await loadObject({ kind: "dataset", id: dataset.id });
  const historical = await loadObject({
    kind: "file",
    id: file.id,
    datasetId: dataset.id,
  });
  expect(current.samples).toEqual([]);
  expect(historical.samples).toHaveLength(1);
});
