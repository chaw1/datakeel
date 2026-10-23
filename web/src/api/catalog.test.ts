import { expect, it } from "vitest";

import { catalogPath, impactPath, metricPath, tablePath } from "./catalog";

it("encodes catalog selections and preserves bounded paging and impact parameters", () => {
  const path = new URL(
    catalogPath("tables", 20, "订单 & amount", "source/one"),
    "http://localhost",
  );
  expect(Object.fromEntries(path.searchParams)).toEqual({
    limit: "20",
    offset: "20",
    search: "订单 & amount",
    parent_id: "source/one",
  });
  expect(tablePath("source/main/orders")).toBe(
    "/api/catalog/tables/source%2Fmain%2Forders",
  );
  expect(metricPath("retail/revenue")).toBe(
    "/api/catalog/metrics/retail%2Frevenue",
  );
  const impact = new URL(
    impactPath("source/main/orders/amount"),
    "http://localhost",
  );
  expect(impact.searchParams.get("asset_id")).toBe("source/main/orders/amount");
  expect(impact.searchParams.get("max_nodes")).toBe("100");
});
