import { useState } from "react";

import { version } from "../../package.json";
import { Icon } from "../components/Icon";
import { useI18n } from "../i18n/useI18n";

import { findNavLocation, navGroups } from "./navigation";

import type { NavGroupId, Page } from "./navigation";
import type { Dataset } from "../api/types";
import type { ObjectKind } from "../features/object/navigation";

export function Sidebar({
  page,
  datasets,
  error,
  pending = 0,
  objectKind,
  collapsed,
  collapsedGroups,
  onToggleCollapsed,
  onToggleGroup,
}: {
  page: Page;
  datasets: Dataset[];
  error: string;
  pending?: number;
  objectKind?: ObjectKind;
  collapsed?: boolean;
  collapsedGroups?: readonly NavGroupId[];
  onToggleCollapsed?: () => void;
  onToggleGroup?: (groupId: NavGroupId) => void;
}) {
  const { t } = useI18n();
  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const [internalGroups, setInternalGroups] = useState<NavGroupId[]>([]);
  const isCollapsed = collapsed ?? internalCollapsed;
  const activeCollapsedGroups = collapsedGroups ?? internalGroups;
  const toggleLabel = t(isCollapsed ? "expandSidebar" : "collapseSidebar");
  const activeItemId = findNavLocation(page, objectKind)?.itemId ?? page;

  function handleToggleCollapsed() {
    if (onToggleCollapsed) onToggleCollapsed();
    else setInternalCollapsed((previous) => !previous);
  }

  function handleToggleGroup(groupId: NavGroupId) {
    if (onToggleGroup) onToggleGroup(groupId);
    else {
      setInternalGroups((previous) =>
        previous.includes(groupId)
          ? previous.filter((id) => id !== groupId)
          : [...previous, groupId],
      );
    }
  }

  return (
    <aside
      className="sidebar"
      data-collapsed={isCollapsed ? "true" : undefined}
    >
      <div className="sidebar-header">
        <a className="brand" href="#/workbench" aria-label={t("datakeelHome")}>
          <span className="brand-mark">
            <span />
            <span />
            <span />
          </span>
          <span className="brand-text">{t("datakeel")}</span>
          <span className="brand-dot">.</span>
        </a>
        <button
          type="button"
          className="sidebar-toggle"
          aria-label={toggleLabel}
          aria-expanded={!isCollapsed}
          title={toggleLabel}
          onClick={() => {
            handleToggleCollapsed();
          }}
        >
          <Icon name="sidebar" size={15} />
        </button>
      </div>
      <nav className="nav" aria-label={t("mainNavigation")}>
        {navGroups.map((group) => {
          const groupCollapsed = activeCollapsedGroups.includes(group.id);
          return (
            <div
              className="nav-group"
              key={group.id}
              data-nav-group={group.id}
              data-group-collapsed={groupCollapsed ? "true" : undefined}
            >
              <button
                type="button"
                className="nav-group-toggle"
                aria-expanded={!groupCollapsed}
                onClick={() => {
                  handleToggleGroup(group.id);
                }}
              >
                <span className="nav-label">{t(group.label)}</span>
                <Icon name="chevron" size={12} />
              </button>
              <div
                className="nav-group-items"
                hidden={!isCollapsed && groupCollapsed}
              >
                {group.items.map((item) => {
                  const isActive =
                    page === item.id ||
                    (activeItemId === item.id && page !== "object");
                  return (
                    <a
                      key={item.id}
                      href={`#/${item.id}`}
                      className={`nav-item ${isActive || activeItemId === item.id ? "active" : ""}`}
                      aria-current={page === item.id ? "page" : undefined}
                      aria-label={t(item.label)}
                      title={t(item.label)}
                    >
                      <Icon name={item.icon} />
                      <span className="nav-item-label">{t(item.label)}</span>
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
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>
      <div className="sidebar-bottom">
        <div
          className="local-note"
          title={t(error ? "apiUnavailable" : "localRuntime")}
        >
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
