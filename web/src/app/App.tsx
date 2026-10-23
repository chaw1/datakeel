import { useState } from "react";

import { useWorkspace } from "../features/datasets/useWorkspace";
import { objectHref } from "../features/object/navigation";
import { ObjectPage } from "../features/object/ObjectPage";
import { useI18n } from "../i18n/useI18n";
import { LibraryPage } from "../pages/LibraryPage";
import { QualityWorkspacePage } from "../pages/QualityWorkspacePage";
import { RunsPage } from "../pages/RunsPage";
import { WorkbenchPage } from "../pages/WorkbenchPage";

import { lineageHref } from "./lineageNavigation";
import { isOperationPage } from "./navigation";
import { OperationsWorkspace } from "./OperationsWorkspace";
import { useRoute } from "./routing";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { useDashboard } from "./useDashboard";
import { useLegacyRoute } from "./useLegacyRoute";

import type { Page, LineageTarget } from "./navigation";
import type { ObjectTab } from "../features/object/navigation";

export default function App() {
  const { t } = useI18n();
  const route = useRoute();
  useLegacyRoute(route);
  const workspace = useWorkspace(undefined, false);
  const dashboard = useDashboard();
  const [conversationId, setConversationId] = useState("");
  const {
    datasets,
    selected,
    selectedId,
    setSelectedId,
    setRefresh,
    loading,
    error,
  } = workspace;
  const page = route.page;
  function navigate(next: Page) {
    const tabs: Partial<Record<Page, ObjectTab>> = {
      overview: "facts",
      files: "files",
      versions: "versions",
      report: "report",
      lineage: "relations",
    };
    const tab = tabs[next];
    if (tab && selectedId)
      window.location.hash = objectHref({
        kind: "dataset",
        id: selectedId,
        tab,
      });
    else
      window.location.hash = `/${next === "tasks" ? "runs?type=pipeline" : next === "action-runs" ? "runs?type=action" : next}`;
  }
  function changed() {
    setRefresh((n) => n + 1);
    dashboard.reload();
  }
  function openReceipt(target: LineageTarget) {
    window.location.hash = lineageHref(target);
    changed();
  }
  return (
    <div className="app-shell">
      <Sidebar
        page={page}
        datasets={datasets}
        pending={dashboard.value.approvals.length}
        error={error || dashboard.error}
      />
      <div className="main-shell">
        <Topbar page={page} navigate={navigate} selected={selected} />
        <main>
          {(error || dashboard.error) && (
            <div className="error-banner" role="alert">
              <span>{error || dashboard.error}</span>
              <button onClick={changed}>{t("retry")}</button>
            </div>
          )}
          {page === "workbench" ? (
            <WorkbenchPage data={dashboard.value} />
          ) : page === "datasets" ? (
            <LibraryPage
              datasets={datasets}
              loading={loading}
              setRefresh={setRefresh}
              setSelectedId={setSelectedId}
              navigate={navigate}
            />
          ) : page === "object" && route.object ? (
            <ObjectPage
              key={`${route.object.kind}:${route.object.id}`}
              target={route.object}
              onDataChanged={changed}
            />
          ) : page === "runs" ? (
            <RunsPage data={dashboard.value} params={route.params} />
          ) : page === "quality" ? (
            <QualityWorkspacePage
              datasets={dashboard.value.datasets}
              alertsOnly={route.params.get("filter") === "alerts"}
            />
          ) : isOperationPage(page) ? (
            <OperationsWorkspace
              key={`${page}:${route.params.toString()}`}
              page={page}
              datasets={datasets}
              datasetId={selectedId}
              conversationId={conversationId}
              onConversation={setConversationId}
              onTrace={(id) => {
                setConversationId(id);
                navigate("traces");
              }}
              onOpenReceipt={openReceipt}
              onDataChanged={changed}
            />
          ) : (
            <p role="status">{t("loadingData")}</p>
          )}
          <footer className="page-footer">
            <span>{t("localWorkspaceFooter")}</span>
            <span>{t("datakeel")}</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
