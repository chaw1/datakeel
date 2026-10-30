import { useI18n } from "../../i18n/useI18n";

import { viewMessages, workbenchViews } from "./model";

import type { WorkbenchView } from "./model";
import type { useLabelingWorkspace } from "./useLabelingWorkspace";

/** One compact row: project, package, progress, role views and the server identity. */
export function ModuleBar({
  workspace,
}: {
  workspace: ReturnType<typeof useLabelingWorkspace>;
}) {
  const { t } = useI18n();
  const { index, project, projectId, packageId, view } = workspace;
  if (!index) return null;
  const personal = project?.project.workflow_tier === "personal";
  const complete =
    project?.progress.counts
      .filter((item) => ["approved", "finalized"].includes(item.state))
      .reduce((sum, item) => sum + item.count, 0) ?? 0;
  const views: WorkbenchView[] =
    project && (personal || workspace.verified)
      ? workbenchViews(personal, project.effective_scopes)
      : [];
  return (
    <div className="wb-module-bar">
      <h1 className="sr-only">{t("wbNav")}</h1>
      <label>
        {t("wbProject")}
        <select
          value={projectId}
          onBlur={() => undefined}
          onChange={(event) => {
            void workspace.selectProject(event.target.value);
          }}
        >
          {index.projects.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {project && (
        <>
          <label>
            {t("wbPackage")}
            <select
              value={packageId}
              onBlur={() => undefined}
              onChange={(event) => {
                void workspace.selectPackage(event.target.value);
              }}
            >
              <option value="">{t("wbAllPackages")}</option>
              {project.packages.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <div className="wb-progress">
            <span>
              {t("wbProgress")} · {complete}/{project.progress.total}
            </span>
            <progress
              aria-label={t("wbProgress")}
              max={Math.max(1, project.progress.total)}
              value={complete}
            />
          </div>
          <nav className="wb-role-nav" aria-label={t("wbNav")}>
            {views.map((id) => (
              <button
                type="button"
                key={id}
                aria-current={view === id ? "page" : undefined}
                onClick={() => {
                  void workspace.selectView(id);
                }}
              >
                {t(viewMessages[id])}
              </button>
            ))}
          </nav>
          <span className="muted wb-actor">
            {t("wbActor", { actor: index.actor })}
          </span>
        </>
      )}
      <button type="button" onClick={workspace.changed}>
        {t("wbRefetch")}
      </button>
    </div>
  );
}
