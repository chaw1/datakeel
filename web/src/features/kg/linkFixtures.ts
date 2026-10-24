import { cedar, relation, sourceRef } from "../../test/kgFixtures";

import type { EntityLink } from "../../api/kg";

export const metricEntity = { ...cedar, name: "营业额", type: "metric" };
export const salesLink: EntityLink = {
  entity: metricEntity,
  assertion: {
    ...relation.assertion,
    id: "sales-link",
    predicate: "link.maps_to",
    status: "candidate",
  },
  target: {
    asset_ref: {
      ...sourceRef,
      asset_id: "sales_revenue",
      asset_type: "metric",
    },
    name: "销售额",
    revision: 1,
  },
  match_kind: "ambiguous",
  basis: ["营业额 exactly matches metric synonym"],
};
export const tableLink: EntityLink = {
  ...salesLink,
  entity: { ...cedar, name: "sales table", type: "dataset" },
  assertion: { ...salesLink.assertion, id: "table-link", status: "accepted" },
  target: {
    asset_ref: {
      ...sourceRef,
      asset_id: "crm/main/sales",
      asset_type: "table",
    },
    name: "sales",
    revision: 1,
  },
  match_kind: "unique",
  basis: ["sales exactly matches table name"],
};
