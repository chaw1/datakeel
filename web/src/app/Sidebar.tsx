import { version } from "../../package.json";
import { Icon } from "../components/Icon";
import { useI18n } from "../i18n/useI18n";

import type { Page } from "./navigation";
import type { Dataset } from "../api/types";

const groups = [
  {
    label: "workbench",
    items: [{ id: "workbench", label: "workbench", icon: "grid" }],
  },
  {
    label: "dataGroup",
    items: [
      { id: "datasets", label: "dataLibraryLabel", icon: "database" },
      { id: "catalog", label: "catalogNav", icon: "database" },
      { id: "standards", label: "stdNav", icon: "grid" },
      { id: "ask", label: "askNav", icon: "message" },
    ],
  },
  {
    label: "evidenceGroup",
    items: [
      { id: "evidence", label: "evidenceNav", icon: "quality" },
      { id: "kg", label: "kgNav", icon: "grid" },
      { id: "quality", label: "dataQuality", icon: "quality" },
    ],
  },
  {
    label: "operationsGroup",
    items: [
      { id: "workflows", label: "workflowsNav", icon: "activity" },
      { id: "approvals", label: "approvalsNav", icon: "check" },
      { id: "runs", label: "runRecords", icon: "activity" },
    ],
  },
  {
    label: "agentsGroup",
    items: [
      { id: "agent", label: "agentNav", icon: "message" },
      { id: "memory", label: "memoryNav", icon: "grid" },
      { id: "traces", label: "tracesNav", icon: "activity" },
    ],
  },
  {
    label: "modelsGroup",
    items: [{ id: "ontology", label: "ontologyNav", icon: "grid" }],
  },
] as const;
export function Sidebar({
  page,
  datasets,
  error,
  pending = 0,
}: {
  page: Page;
  datasets: Dataset[];
  error: string;
  pending?: number;
}) {
  const { t } = useI18n();
  return (
    <aside className="sidebar">
      <a className="brand" href="#/workbench" aria-label={t("datakeelHome")}>
        <span className="brand-mark">
          <span />
          <span />
          <span />
        </span>
        {t("datakeel")}
        <span className="brand-dot">.</span>
      </a>
      <nav className="nav" aria-label={t("mainNavigation")}>
        {groups.map((group) => (
          <div
            className="nav-group"
            key={group.label}
            data-nav-group={group.label}
          >
            <span className="nav-label">{t(group.label)}</span>
            {group.items.map((item) => (
              <a
                key={item.id}
                href={`#/${item.id}`}
                className={`nav-item ${page === item.id ? "active" : ""}`}
                aria-current={page === item.id ? "page" : undefined}
                aria-label={t(item.label)}
                title={t(item.label)}
              >
                <Icon name={item.icon} />
                <span>{t(item.label)}</span>
                {item.id === "datasets" && (
                  <span className="nav-count">{datasets.length}</span>
                )}
                {item.id === "approvals" && (
                  <span
                    className="nav-count"
                    aria-label={t("workingCount", { count: pending })}
                    data-pending-count={pending}
                  >
                    {pending}
                  </span>
                )}
              </a>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="local-note">
          <span className={error ? "status-dot offline" : "status-dot"} />
          <strong>{t(error ? "apiUnavailable" : "localRuntime")}</strong>
        </div>
        <div className="sidebar-footer">
          <span>{t("datakeel")}</span>
          <span>{`v${version}`}</span>
        </div>
      </div>
    </aside>
  );
}
