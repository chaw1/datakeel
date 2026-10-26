import { vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";
import { report as analysisReport } from "../../test/fixtures";

import type {
  CodeList,
  FieldStandard,
  MappingSuggestion,
  StandardsCoverage,
  StandardsHistory,
  StandardsReport,
} from "../../api/standards";
import type { ActionPlan } from "../../api/types";

export const standard: FieldStandard = {
  code: "customer_id",
  name_zh: "客户编号",
  name_en: "Customer identifier",
  description: "Stable customer business identifier.",
  data_type: "string",
  length: 12,
  status: "active",
  owner: "Customer operations",
  version: 1,
  sensitivity: "internal",
  required: true,
  aliases: ["cust_no"],
};
export const codeList: CodeList = {
  code: "customer_status",
  name: "Customer status",
  version: 1,
  status: "active",
  entries: [
    { value: "A", label_zh: "有效", label_en: "Active" },
    { value: "I", label_zh: "停用", label_en: "Inactive" },
  ],
};
const overall = {
  key: "all",
  total_columns: 4,
  mapped_columns: 2,
  compliant_columns: 1,
  coverage: 0.5,
  compliance: 0.5,
};
export const coverage: StandardsCoverage = {
  overall,
  sources: [{ ...overall, key: "retail" }],
  tables: [{ ...overall, key: "retail/main/customers" }],
  owners: [{ ...overall, key: "Customer operations" }],
  violation_top: [
    {
      column_id: "retail/main/customers/cust_no",
      standard_code: "customer_id",
      violation_count: 1,
      rules: ["length"],
    },
  ],
};
export const suggestions: MappingSuggestion[] = [
  {
    column_id: "retail/main/customers/cust_no",
    candidates: [
      {
        standard_code: "customer_id",
        score: 0.95,
        reasons: [
          "Column tokens match customer identifier",
          "string type is compatible",
        ],
      },
    ],
  },
  { column_id: "retail/main/customers/opaque_payload", candidates: [] },
];
export const standardsReport: StandardsReport = {
  profiles: [
    {
      column_id: suggestions[0].column_id,
      name: "cust_no",
      truncated: false,
      values: [],
      null_count: 0,
      row_count: 10,
      data_type: "string",
      table_id: "retail/main/customers",
      source_id: "retail",
      owner: "Customer operations",
    },
  ],
  mappings: [
    { column_id: suggestions[0].column_id, standard_code: "customer_id" },
  ],
  coverage,
  checks: [
    {
      column_id: suggestions[0].column_id,
      standard_code: "customer_id",
      row_count: 10,
      compliant: false,
      fully_checked: true,
      checked_rules: ["length", "type", "required"],
      skipped_rules: [],
      violations: [
        {
          rule: "length",
          count: 1,
          message: "Maximum customer identifier length exceeded",
          samples: ["[REDACTED]"],
        },
      ],
    },
  ],
};
export const standardsPlan: ActionPlan = {
  ...actionPlan,
  action_type: "confirm_standard_mapping",
  reversible: true,
  external: false,
  canonical_params: { mapping: standardsReport.mappings[0] },
  manifest: { ...actionPlan.manifest, objects: [], total_bytes: 0 },
};
export const history: StandardsHistory = {
  revisions: [1, 2].map((revision) => ({
    revision,
    contract: {
      standards: [{ ...standard, version: revision }],
      code_lists: [codeList],
    },
    mappings: standardsReport.mappings,
    plan_id: "plan-1",
    actor: "local",
    action_type: "update_standard",
    event_id: "event-1",
    created_at: "2026-10-27T00:00:00Z",
  })),
};
export function mockStandardsFetch() {
  const fetch = vi.fn<(input: string, init?: RequestInit) => Promise<Response>>(
    (input) => {
      const url = new URL(input, "http://localhost");
      let payload: unknown = [];
      const path = url.pathname;
      if (path === "/api/standards/fields") payload = [standard];
      if (path === "/api/standards/code-lists") payload = [codeList];
      if (path === "/api/standards/suggestions") payload = suggestions;
      if (path === "/api/standards/profiles")
        payload = standardsReport.profiles;
      if (path === "/api/standards/mappings") payload = [];
      if (path === "/api/standards/coverage") payload = coverage;
      if (path === "/api/standards/report") payload = standardsReport;
      if (path === "/api/standards/history") payload = history;
      if (path === "/api/standards/quality")
        payload = {
          total: 50,
          grade: "poor",
          column_count: 4,
          mapped_columns: 2,
          fully_checked_columns: 2,
          skipped_rules: 0,
          dimensions: {
            completeness: {
              score: 100,
              checked_rules: 2,
              failed_rules: 0,
              violation_count: 0,
              weight: 1,
            },
          },
          issues: [],
        };
      if (path === "/api/standards/analysis-report") payload = analysisReport;
      if (path.endsWith("/prepare"))
        payload = { ...standardsPlan, action_type: path.split("/").at(-2) };
      if (path.startsWith("/api/approvals/"))
        payload = { ...standardsPlan, status: "APPROVED" };
      if (path.endsWith("/execute"))
        payload = { ...actionRun, action_type: "confirm_standard_mapping" };
      return Promise.resolve(new Response(JSON.stringify(payload)));
    },
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
