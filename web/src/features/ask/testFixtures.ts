import type { AskAnswer, AskMetric } from "../../api/ask";

export const retailMetric: AskMetric = {
  status: "resolved",
  reasons: [],
  definition: {
    number_format: "number",
    id: "retail_revenue",
    name: "零售额",
    description: "Consumer retail revenue from completed orders.",
    owner: "retail-operations",
    version: 2,
    measure: {
      table: "ecommerce/main/orders",
      column: "ecommerce/main/orders/amount",
      aggregation: "sum",
    },
    time: { column: "ecommerce/main/orders/date", granularity: "day" },
    filters: [
      { column: "ecommerce/main/orders/status", op: "eq", value: "completed" },
    ],
    caveats: ["Excludes cancelled orders."],
  },
};

export const retailAnswer: AskAnswer = {
  answer_kind: "metric",
  subject_candidates: [],
  id: "answer-1",
  session_id: "session-1",
  question: "上个季度华东区零售额是多少",
  interpreted_question: "上个季度华东区零售额是多少",
  status: "answered",
  message: "Calculated from the registered definition.",
  reference_instant: "2026-10-01T00:00:00Z",
  metric_card: retailMetric,
  sql: {
    metric_id: "retail_revenue",
    metric_version: 2,
    source_id: "ecommerce",
    dialect: "sqlite",
    sql: "SELECT SUM(amount) AS value FROM orders WHERE region = :region",
    parameters: { region: "华东", start: "2026-07-01", end: "2026-10-01" },
    tables: ["ecommerce/main/orders"],
    columns: ["ecommerce/main/orders/amount", "ecommerce/main/orders/region"],
  },
  result: { columns: ["value"], rows: [[4979475]], truncated: false },
  time_range: { start: "2026-07-01", end: "2026-10-01" },
  matches: [
    {
      start: 0,
      end: 4,
      text: "上个季度",
      source: "time:last_quarter",
      match_kind: "time",
    },
    {
      start: 4,
      end: 6,
      text: "华东",
      source: "dimension:region",
      match_kind: "dimension_value",
      dimension_id: "region",
    },
    {
      start: 7,
      end: 10,
      text: "零售额",
      source: "metric:retail_revenue",
      match_kind: "exact",
      metric_id: "retail_revenue",
    },
  ],
  candidates: [],
  lineage: {
    asset_id: "retail_revenue",
    hops: 2,
    max_nodes: 30,
    include_catalog: true,
  },
  assertion_ids: ["assertion-1"],
  assertions: [],
};

export const candidateMetrics: AskMetric[] = [
  retailMetric,
  {
    ...retailMetric,
    definition: {
      ...retailMetric.definition,
      id: "sales_revenue",
      name: "销售额",
      owner: "sales-operations",
    },
  },
  {
    ...retailMetric,
    definition: {
      ...retailMetric.definition,
      id: "shipment_revenue",
      name: "出货额",
      owner: "supply-operations",
    },
  },
];

export const unavailableAnswer: AskAnswer = {
  answer_kind: "metric",
  subject_candidates: [],
  id: "answer-2",
  session_id: "session-1",
  question: "退货率为什么上升",
  interpreted_question: "退货率为什么上升",
  status: "unanswerable",
  message: "This question is outside the registered metric definitions.",
  reference_instant: "2026-10-01T00:00:00Z",
  matches: [],
  candidates: candidateMetrics,
  assertions: [],
  assertion_ids: ["assertion-2"],
};
