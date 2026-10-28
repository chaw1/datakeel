import { expect, it } from "vitest";

import { readRoute } from "./routing";

it("loads every canonical workspace URL independently of app state", () => {
  for (const page of [
    "workbench",
    "datasets",
    "catalog",
    "ask",
    "evidence",
    "quality",
    "approvals",
    "runs",
    "agent",
    "traces",
    "ontology",
    "workflows",
    "custom-operators",
  ]) {
    window.history.replaceState(null, "", `/#/${page}?type=action`);
    expect(readRoute().page).toBe(page);
    expect(readRoute().params.get("type")).toBe("action");
  }
});
it("restores a percent-encoded catalog object and relation filter", () => {
  window.history.replaceState(
    null,
    "",
    "/#/object/table/ecommerce%2Fmain%2Forders?tab=relations&relation=derived",
  );
  expect(readRoute().object).toMatchObject({
    kind: "table",
    id: "ecommerce/main/orders",
    tab: "relations",
    relation: "derived",
  });
});
it("recognizes old HTTP and hash lineage entrances for redirect resolution", () => {
  window.history.replaceState(null, "", "/lineage?asset=abc");
  expect(readRoute().legacy?.assetId).toBe("abc");
  window.history.replaceState(
    null,
    "",
    "/#lineage?asset_id=retail_revenue&include_catalog=true",
  );
  expect(readRoute().legacy?.assetId).toBe("retail_revenue");
});

it("canonicalizes old report and run URLs while retaining their filters", () => {
  for (const path of ["/tasks?state=RUNNING", "/#tasks?state=RUNNING"]) {
    window.history.replaceState(null, "", path);
    expect(readRoute().redirect).toBe("#/runs?state=RUNNING&type=pipeline");
  }
  window.history.replaceState(null, "", "/action-runs");
  expect(readRoute().redirect).toBe("#/runs?type=action");
  window.history.replaceState(null, "", "/report?dataset=dataset-1");
  expect(readRoute().redirect).toBe("#/object/dataset/dataset-1?tab=report");
  window.history.replaceState(null, "", "/lineage?asset=unknown#/workbench");
  expect(readRoute().page).toBe("workbench");
});
