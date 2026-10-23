import { expect, it } from "vitest";

import { lineageHref, readLineageTarget } from "./lineageNavigation";

it("restores sample subgraph links while preserving receipt link behavior", () => {
  const target = {
    assetId: "sample",
    datasetId: "dataset",
    includeSemantic: true,
  };
  const href = lineageHref(target);
  expect(href).toContain("asset_id=sample");
  expect(readLineageTarget(href)).toEqual({ ...target, eventId: "" });
  expect(lineageHref({ assetId: "receipt" })).toContain("asset=receipt");
  expect(readLineageTarget("#lineage?asset=receipt")).toEqual({
    assetId: "receipt",
    datasetId: undefined,
    eventId: undefined,
  });
});

it("round-trips catalog links without enabling the semantic overlay", () => {
  const href = lineageHref({
    assetId: "shop/main/orders/paid",
    includeCatalog: true,
  });
  expect(href).toContain("include_catalog=true");
  expect(readLineageTarget(href)).toEqual({
    assetId: "shop/main/orders/paid",
    includeCatalog: true,
    eventId: "",
    datasetId: "",
  });
});
