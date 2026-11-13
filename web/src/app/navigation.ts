import type { IconName } from "../components/Icon";
import type { ObjectKind, ObjectTab } from "../features/object/navigation";
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

export interface NavItem {
  readonly id: Page;
  readonly label: MessageKey;
  readonly icon: IconName;
}

export const navGroups = [
  {
    id: "workbench",
    label: "workbench",
    items: [
      { id: "workbench", label: "workbench", icon: "workbench" },
      { id: "labeling", label: "wbNav", icon: "annotation" },
    ],
  },
  {
    id: "dataGroup",
    label: "dataGroup",
    items: [
      { id: "datasets", label: "dataLibraryLabel", icon: "database" },
      { id: "catalog", label: "catalogNav", icon: "catalog" },
      { id: "data-assets", label: "assetMarket", icon: "asset" },
      { id: "standards", label: "stdNav", icon: "standards" },
      { id: "ask", label: "askNav", icon: "ask" },
    ],
  },
  {
    id: "evidenceGroup",
    label: "evidenceGroup",
    items: [
      { id: "evidence", label: "evidenceNav", icon: "evidence" },
      { id: "kg", label: "kgNav", icon: "kg" },
      { id: "quality", label: "dataQuality", icon: "quality" },
      { id: "quality-rules", label: "dqNav", icon: "rules" },
    ],
  },
  {
    id: "operationsGroup",
    label: "operationsGroup",
    items: [
      { id: "custom-operators", label: "customOperatorsNav", icon: "operator" },
      { id: "workflows", label: "workflowsNav", icon: "workflow" },
      { id: "approvals", label: "approvalsNav", icon: "check" },
      { id: "runs", label: "runRecords", icon: "activity" },
    ],
  },
  {
    id: "agentsGroup",
    label: "agentsGroup",
    items: [
      { id: "agent", label: "agentNav", icon: "agent" },
      { id: "memory", label: "memoryNav", icon: "memory" },
      { id: "traces", label: "tracesNav", icon: "trace" },
    ],
  },
  {
    id: "modelsGroup",
    label: "modelsGroup",
    items: [{ id: "ontology", label: "ontologyNav", icon: "ontology" }],
  },
] as const;

export type NavGroupId = (typeof navGroups)[number]["id"];

export const objectTabLabels: Record<ObjectTab, MessageKey> = {
  facts: "objFacts",
  relations: "objRelations",
  evidence: "objEvidence",
  history: "objHistory",
  files: "filesTab",
  versions: "versions",
  quality: "quality",
  "annotation-quality": "annotationQuality",
  "text-governance": "llmDataTitle",
  report: "report",
  datasheets: "datasheets",
};

export function parentRouteForObject(kind: ObjectKind): {
  groupId: NavGroupId;
  groupLabel: MessageKey;
  page: Page;
  label: MessageKey;
} {
  if (kind === "dataset" || kind === "file" || kind === "version") {
    return {
      groupId: "dataGroup",
      groupLabel: "dataGroup",
      page: "datasets",
      label: "dataLibraryLabel",
    };
  }
  if (kind === "table" || kind === "column" || kind === "metric") {
    return {
      groupId: "dataGroup",
      groupLabel: "dataGroup",
      page: "catalog",
      label: "catalogNav",
    };
  }
  if (kind === "term") {
    return {
      groupId: "dataGroup",
      groupLabel: "dataGroup",
      page: "standards",
      label: "stdNav",
    };
  }
  return {
    groupId: "operationsGroup",
    groupLabel: "operationsGroup",
    page: "runs",
    label: "runRecords",
  };
}

export function findNavLocation(
  page: Page,
  objectKind?: ObjectKind,
):
  | {
      groupId: NavGroupId;
      groupLabel: MessageKey;
      itemId: Page;
      itemLabel: MessageKey;
    }
  | undefined {
  if (page === "object" && objectKind) {
    const parent = parentRouteForObject(objectKind);
    return {
      groupId: parent.groupId,
      groupLabel: parent.groupLabel,
      itemId: parent.page,
      itemLabel: parent.label,
    };
  }
  if (page === "tasks" || page === "action-runs") {
    return {
      groupId: "operationsGroup",
      groupLabel: "operationsGroup",
      itemId: "runs",
      itemLabel: "runRecords",
    };
  }
  if (
    [
      "overview",
      "files",
      "versions",
      "lineage",
      "report",
      "datasheets",
    ].includes(page)
  ) {
    return {
      groupId: "dataGroup",
      groupLabel: "dataGroup",
      itemId: "datasets",
      itemLabel: "dataLibraryLabel",
    };
  }
  for (const group of navGroups) {
    const match = group.items.find((item) => item.id === page);
    if (match) {
      return {
        groupId: group.id,
        groupLabel: group.label,
        itemId: match.id,
        itemLabel: match.label,
      };
    }
  }
  return undefined;
}

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
