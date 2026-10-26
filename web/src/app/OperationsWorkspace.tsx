import { ActionRunsPage } from "../pages/ActionRunsPage";
import { AgentPage } from "../pages/AgentPage";
import { ApprovalsPage } from "../pages/ApprovalsPage";
import { AskPage } from "../pages/AskPage";
import { CatalogPage } from "../pages/CatalogPage";
import { EvidencePage } from "../pages/EvidencePage";
import { KnowledgeGraphPage } from "../pages/KnowledgeGraphPage";
import { MemoryPage } from "../pages/MemoryPage";
import { OntologyPage } from "../pages/OntologyPage";
import { StandardsPage } from "../pages/StandardsPage";
import { TracesPage } from "../pages/TracesPage";
import { WorkflowsPage } from "../pages/WorkflowsPage";

import type { LineageTarget, OperationPage } from "./navigation";
import type { Dataset } from "../api/types";
export function OperationsWorkspace({
  page,
  onOpenReceipt,
  onDataChanged,
  datasets,
  datasetId,
  conversationId,
  onConversation,
  onTrace,
}: {
  page: OperationPage;
  datasets: Dataset[];
  datasetId: string;
  conversationId: string;
  onConversation: (id: string) => void;
  onTrace: (id: string) => void;
  onOpenReceipt: (target: LineageTarget) => void;
  onDataChanged: () => void;
}) {
  if (page === "kg")
    return (
      <KnowledgeGraphPage
        datasets={datasets}
        datasetId={datasetId}
        onDataChanged={onDataChanged}
        onOpenReceipt={onOpenReceipt}
      />
    );
  if (page === "standards")
    return (
      <StandardsPage
        onOpenReceipt={onOpenReceipt}
        onDataChanged={onDataChanged}
      />
    );
  if (page === "memory") return <MemoryPage datasets={datasets} />;
  if (page === "workflows")
    return <WorkflowsPage datasets={datasets} onDataChanged={onDataChanged} />;
  if (page === "catalog")
    return (
      <CatalogPage
        onOpenReceipt={onOpenReceipt}
        onDataChanged={onDataChanged}
      />
    );
  if (page === "ask") return <AskPage onOpenReceipt={onOpenReceipt} />;
  if (page === "evidence")
    return (
      <EvidencePage
        datasets={datasets}
        datasetId={datasetId}
        onDataChanged={onDataChanged}
        onOpenReceipt={onOpenReceipt}
      />
    );
  if (page === "agent")
    return (
      <AgentPage
        datasets={datasets}
        datasetId={datasetId}
        conversationId={conversationId}
        onConversation={onConversation}
        onTrace={onTrace}
        onDataChanged={onDataChanged}
        onOpenReceipt={onOpenReceipt}
      />
    );
  if (page === "traces")
    return (
      <TracesPage
        conversationId={conversationId}
        onConversation={onConversation}
      />
    );
  if (page === "approvals")
    return (
      <ApprovalsPage
        onOpenReceipt={onOpenReceipt}
        onDataChanged={onDataChanged}
      />
    );
  if (page === "action-runs")
    return <ActionRunsPage onOpenReceipt={onOpenReceipt} />;
  return <OntologyPage />;
}
