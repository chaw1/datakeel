import type { DqRule } from "../../api/qualityRules";

export function numberInput(value: number): number | "" {
  return Number.isFinite(value) ? value : "";
}

export function newRule(): DqRule {
  return {
    id: "",
    name: "",
    target: { source_id: "", table: "", column: null, schema_name: null },
    kind: "not_null",
    revision: 1,
    owner: "local",
    severity: "error",
    threshold: 0,
    cron: null,
    dataset_id: null,
    timeout_ms: 5000,
    max_rows: 10000,
    enabled: true,
  };
}
