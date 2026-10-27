import type { DqIssue, DqResult, DqRule } from "../../api/qualityRules";
import type { MessageKey } from "../../i18n/en";

export const ruleKinds: Record<DqRule["kind"], MessageKey> = {
  not_null: "dqNotNull",
  unique: "dqUnique",
  range: "dqRange",
  accepted_values: "dqAcceptedValues",
  regex: "dqRegex",
  referential_integrity: "dqReferential",
  freshness: "dqFreshness",
  volume_change: "dqVolume",
  distribution_drift: "dqDrift",
  sql_assertion: "dqSql",
};

export const resultStatuses: Record<DqResult["status"], MessageKey> = {
  passed: "dqPassed",
  failed: "dqFailed",
  baseline_insufficient: "dqBaseline",
  error: "dqExecutionError",
};

export const issueStatuses: Record<DqIssue["status"], MessageKey> = {
  open: "dqOpen",
  claimed: "dqClaimed",
  resolved: "dqResolved",
  recovered: "dqRecovered",
};

export const parameterExamples: Record<DqRule["kind"], string> = {
  not_null: "{}",
  unique: "{}",
  range: '{"minimum": 0}',
  accepted_values: '{"values": ["active", "pending"]}',
  regex: '{"pattern": "^[A-Z]+$"}',
  referential_integrity:
    '{"reference_table": "customers", "reference_column": "id"}',
  freshness: "{}",
  volume_change: '{"baseline_runs": 3}',
  distribution_drift: '{"baseline_runs": 3, "statistic": "mean"}',
  sql_assertion:
    '{"sql": "SELECT * FROM orders WHERE amount < :minimum", "bindings": {"minimum": 0}}',
};

export function ruleTarget(rule: DqRule) {
  return [
    rule.target.source_id,
    rule.target.schema_name,
    rule.target.table,
    rule.target.column,
  ]
    .filter(Boolean)
    .join(" / ");
}
