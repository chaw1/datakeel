import type { ActionPlan } from "../../api/types";
import type { MessageKey } from "../../i18n/en";

export const approvalActions: Record<ActionPlan["action_type"], MessageKey> = {
  create_data_asset: "assetNew",
  update_data_asset: "assetEdit",
  publish_data_asset: "assetPublish",
  withdraw_data_asset: "assetWithdraw",
  decide_asset_application: "assetDecision",
  revoke_asset_grant: "assetRevoke",
  delete_files: "approvalDelete",
  export_dataset: "approvalExport",
  quarantine_files: "approvalQuarantine",
  unquarantine_files: "approvalUnquarantine",
  create_version_from_selection: "approvalVersion",
  run_pipeline: "approvalPipeline",
  run_kg_extraction: "kgExtractAction",
  save_metadata: "approvalMetadata",
  decide_assertions: "approvalAssertions",
  import_catalog: "approvalImport",
  restore_catalog: "approvalRestore",
  update_metric: "approvalMetricUpdate",
  rollback_metric: "approvalMetricRollback",
  update_term: "approvalTermUpdate",
  rollback_term: "approvalTermRollback",
};
