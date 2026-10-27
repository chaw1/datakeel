import type { MessageKey } from "../i18n/en";
export type Page =
  | "workbench"
  | "runs"
  | "object"
  | "datasets"
  | "overview"
  | "files"
  | "versions"
  | "tasks"
  | "lineage"
  | "quality"
  | "report"
  | "datasheets"
  | "approvals"
  | "action-runs"
  | "ontology"
  | "evidence"
  | "kg"
  | "agent"
  | "catalog"
  | "ask"
  | "traces"
  | "workflows"
  | "memory";
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
  { id: "workflows", label: "workflowsNav", icon: "activity" },
  { id: "catalog", label: "catalogNav", icon: "database" },
  { id: "ask", label: "askNav", icon: "message" },
  { id: "evidence", label: "evidenceNav", icon: "quality" },
  { id: "kg", label: "kgNav", icon: "grid" },
  { id: "agent", label: "agentNav", icon: "message" },
  { id: "memory", label: "memoryNav", icon: "grid" },
  { id: "approvals", label: "approvalsNav", icon: "check" },
  { id: "action-runs", label: "actionRunsNav", icon: "activity" },
  { id: "traces", label: "tracesNav", icon: "activity" },
  { id: "ontology", label: "ontologyNav", icon: "grid" },
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
