import type { MessageKey } from "../i18n/en";
export type Page =
  | "workbench"
  | "labeling"
  | "runs"
  | "object"
  | "datasets"
  | "overview"
  | "files"
  | "versions"
  | "tasks"
  | "lineage"
  | "quality"
  | "quality-rules"
  | "report"
  | "datasheets"
  | "approvals"
  | "action-runs"
  | "ontology"
  | "evidence"
  | "kg"
  | "agent"
  | "data-assets"
  | "catalog"
  | "ask"
  | "traces"
  | "workflows"
  | "memory"
  | "custom-operators"
  | "standards";
// Enterprise workspaces remain independent of the file dataset selection.
export const tabs: { id: Page; label: MessageKey }[] = [
  { id: "overview", label: "overview" },
  { id: "files", label: "filesTab" },
  { id: "versions", label: "versions" },
  { id: "lineage", label: "lineage" },
  { id: "quality", label: "quality" },
  { id: "report", label: "report" },
  { id: "datasheets", label: "datasheets" },
];

export const operationPages = [
  { id: "custom-operators", label: "customOperatorsNav", icon: "operator" },
  { id: "data-assets", label: "assetMarket", icon: "asset" },
  { id: "workflows", label: "workflowsNav", icon: "workflow" },
  { id: "catalog", label: "catalogNav", icon: "catalog" },
  { id: "standards", label: "stdNav", icon: "standards" },
  { id: "ask", label: "askNav", icon: "ask" },
  { id: "evidence", label: "evidenceNav", icon: "evidence" },
  { id: "kg", label: "kgNav", icon: "kg" },
  { id: "agent", label: "agentNav", icon: "agent" },
  { id: "memory", label: "memoryNav", icon: "memory" },
  { id: "approvals", label: "approvalsNav", icon: "check" },
  { id: "action-runs", label: "actionRunsNav", icon: "activity" },
  { id: "traces", label: "tracesNav", icon: "trace" },
  { id: "ontology", label: "ontologyNav", icon: "ontology" },
] as const;
export type OperationPage = (typeof operationPages)[number]["id"];
export function isOperationPage(page: Page): page is OperationPage {
  return operationPages.some((item) => item.id === page);
}
export type LineageTarget = {
  datasetId?: string;
  eventId?: string;
  assetId?: string;
  includeSemantic?: boolean;
  includeCatalog?: boolean;
};
