import type { components } from "./generated";

export type Dataset = components["schemas"]["DatasetView"];
export type FileItem = components["schemas"]["FileView"];
export type Version = components["schemas"]["VersionView"];
export type Task = components["schemas"]["TaskView"];
export type GraphNode = components["schemas"]["GraphNode"];
export type GraphEdge = components["schemas"]["GraphEdge"];
export type Graph = components["schemas"]["GraphView"];
export type LineageEvent = components["schemas"]["LineageEvent"];
export type Quality = components["schemas"]["QualityView"];
export type Report = components["schemas"]["ReportView"];
export type DatasetData = {
  files: FileItem[];
  versions: Version[];
  tasks: Task[];
  graph: Graph;
  quality: Quality | null;
  report: Report | null;
  errors: string[];
};
export type ActionPlan = components["schemas"]["ActionPlan"];
export type ActionRun = components["schemas"]["ActionRun"];
export type OntologyRegistry = components["schemas"]["OntologyRegistry"];

export type Conversation = components["schemas"]["ConversationView"];
export type AgentEvent = components["schemas"]["AgentEvent"];
export type ConversationCreate =
  components["schemas"]["ConversationCreate-Input"];
export type MessageInput = components["schemas"]["MessageInput"];
export type ModelCallTrace = components["schemas"]["ModelCallTrace"];
export type CostSummary = components["schemas"]["CostSummary"];
export type EvidenceQuery = components["schemas"]["EvidenceQuery"];
export type EvidenceQueryResult = components["schemas"]["EvidenceQueryResult"];
export type EvidenceSample = components["schemas"]["EvidenceSample"];
export type Assertion = components["schemas"]["Assertion"];
export type DecideAssertionsParams =
  components["schemas"]["DecideAssertionsParams"];
