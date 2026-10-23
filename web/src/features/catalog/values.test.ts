import { expect, it } from "vitest";

import { column, impact, metricObject, term } from "./fixtures";
import {
  filterValue,
  impactBranches,
  propertyText,
  serializeFilterValue,
  synonyms,
  termTarget,
} from "./values";

it("builds downstream branches with measured fields, metric terms and cycle protection", () => {
  const branches = impactBranches({
    ...impact,
    links: [
      ...impact.links,
      { source: term.asset_ref, target: column.asset_ref, kind: "derived" },
    ],
  });
  const metricBranch = branches.find(
    (branch) =>
      branch.item.asset_ref.asset_id === metricObject.asset_ref.asset_id,
  );
  expect(metricBranch?.children.map((branch) => branch.item.name)).toEqual([
    "Retail",
  ]);
  expect(metricBranch?.children[0]?.children).toEqual([]);
});

it("narrows open catalog properties and retains typed filter values", () => {
  expect(propertyText(column, "data_type")).toBe("INTEGER");
  expect(propertyText(column, "nullable")).toBe("");
  expect(synonyms(term)).toEqual(["Retail receipts"]);
  expect(termTarget(term)).toBe("retail_revenue");
  expect(
    ["12.5", "true", "false", "null", " completed "].map(filterValue),
  ).toEqual([12.5, true, false, null, "completed"]);
  expect(serializeFilterValue([1, "completed"])).toBe("1, completed");
});
