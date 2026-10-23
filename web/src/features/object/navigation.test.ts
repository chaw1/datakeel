import { expect, it } from "vitest";

import { objectHref, readObjectTarget } from "./navigation";

it("round trips canonical object paths with slash identities and source context", () => {
  const target = {
    kind: "column",
    id: "source/main/order/amount",
    datasetId: "data-1",
    versionId: "v-2",
    tab: "history",
    eventId: "event-3",
    relation: "derived",
    section: "source",
  } as const;
  expect(objectHref(target)).toMatch(/^#\/object\/column\/source%2F/);
  expect(readObjectTarget(objectHref(target))).toEqual(target);
});
it.each([
  "#/object/nope/a",
  "#/object/file/%E0%A4",
  "#/object/dataset/",
  "#/catalog",
])("rejects malformed object route %s", (hash) => {
  expect(readObjectTarget(hash)).toBeUndefined();
});
