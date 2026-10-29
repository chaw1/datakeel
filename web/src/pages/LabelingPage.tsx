import { useState } from "react";

import { mutateProduction, actionDetails } from "../features/labeling/actions";
import { FinalizationPanel } from "../features/labeling/FinalizationPanel";
import {
  allowed,
  viewMessages,
  workbenchViews,
} from "../features/labeling/model";
import { ProjectCockpit } from "../features/labeling/ProjectCockpit";
import { TaskList } from "../features/labeling/TaskList";
import { TaskSession } from "../features/labeling/TaskSession";
import { TemplateEditor } from "../features/labeling/TemplateEditor";
import { useLabelingWorkspace } from "../features/labeling/useLabelingWorkspace";
import { useI18n } from "../i18n/useI18n";

import "../features/labeling/workbench.css";

export function LabelingPage({ params }: { params: URLSearchParams }) {
  const { t } = useI18n();
  const workspace = useLabelingWorkspace(params);
  const { index, project, task, projectId, view, error, busy, page } =
    workspace;
  const [actionError, setActionError] = useState("");
  const [claiming, setClaiming] = useState(false);
  const packageId = workspace.packageId;
  const personal = project?.project.workflow_tier === "personal";
  const scopes = project?.effective_scopes;
  const can = (scope: string) =>
    workspace.verified && !!scopes && allowed(scopes, scope);
  async function claim() {
    if (!project || claiming) return;
    setClaiming(true);
    setActionError("");
    try {
      const run = await mutateProduction("claim_task", {
        project_id: projectId,
        stage: view === "reviews" ? "review" : "annotation",
        ...(packageId ? { package_id: packageId } : {}),
      });
      const details = actionDetails(run);
      if (
        details &&
        typeof details === "object" &&
        "id" in details &&
        typeof details.id === "string"
      ) {
        workspace.cache.invalidate(details.id);
        await workspace.open(details.id);
      }
      workspace.changed();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : t("wbError"));
    } finally {
      setClaiming(false);
    }
  }
  const approved =
    project?.progress.counts.find((item) => item.state === "approved")?.count ??
    0;
  const complete =
    project?.progress.counts
      .filter((item) => ["approved", "finalized"].includes(item.state))
      .reduce((sum, item) => sum + item.count, 0) ?? 0;
  return (
    <div className="wb-page">
      <header className="page-heading">
        <div>
          <p className="eyebrow">{t("wbNav")}</p>
          <h1 className="page-title">{t("wbTitle")}</h1>
          <p className="muted">{t("wbDescription")}</p>
        </div>
      </header>
      {(error || actionError) && (
        <p role="alert" className="error-banner">
          {error || actionError}
        </p>
      )}
      {!index ? (
        <p role="status">{t("wbLoading")}</p>
      ) : !index.projects.length ? (
        <p className="empty-state">{t("wbNoProjects")}</p>
      ) : (
        <>
          <div className="wb-module-bar">
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
              </>
            )}
            <button type="button" onClick={workspace.changed}>
              {t("wbRefetch")}
            </button>
          </div>
          {project && (
            <>
              <p className="muted">{t("wbActor", { actor: index.actor })}</p>
              <nav className="wb-role-nav" aria-label={t("wbNav")}>
                {(personal || workspace.verified
                  ? workbenchViews(personal, project.effective_scopes)
                  : []
                ).map((id) => (
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
              {busy && <p role="status">{t("wbLoading")}</p>}
              {task ? (
                <TaskSession
                  key={`${index.actor}:${task.task.id}`}
                  task={task}
                  actor={index.actor}
                  canSync={workspace.verified}
                  isIdentityVerified={workspace.isIdentityVerified}
                  project={project}
                  onNavigate={(direction) => {
                    void workspace.navigate(direction);
                  }}
                  onChanged={() => {
                    workspace.cache.invalidate(task.task.id);
                    workspace.changed();
                  }}
                  onSnapshot={workspace.receiveTask}
                  registerGuard={workspace.registerGuard}
                />
              ) : view === "cockpit" ? (
                <ProjectCockpit data={project} />
              ) : (
                <>
                  <div className="wb-list-heading">
                    <h2>
                      {t(
                        personal
                          ? "wbMyData"
                          : view === "reviews"
                            ? "wbReviewQueue"
                            : "wbMyTasks",
                      )}
                    </h2>
                    {!personal &&
                      can("production:claim") &&
                      can(
                        view === "reviews"
                          ? "production:review"
                          : "production:annotate",
                      ) && (
                        <button
                          type="button"
                          className="button primary"
                          disabled={claiming}
                          onClick={() => {
                            void claim();
                          }}
                        >
                          {t(view === "reviews" ? "wbClaimReview" : "wbClaim")}
                        </button>
                      )}
                  </div>
                  <TaskList
                    tasks={project.tasks}
                    risks={project.task_risks}
                    onOpen={(item) => {
                      void workspace.open(item.id);
                    }}
                  />
                  <div className="wb-pagination">
                    <button
                      type="button"
                      disabled={page === 0}
                      onClick={() => {
                        void workspace.paginate(-1);
                      }}
                    >
                      {t("wbPageBack")}
                    </button>
                    <span>{t("wbPage", { page: page + 1 })}</span>
                    <button
                      type="button"
                      disabled={!project.next_cursor}
                      onClick={() => {
                        void workspace.paginate(1);
                      }}
                    >
                      {t("wbLoadMore")}
                    </button>
                  </div>
                </>
              )}
              {!task && can("production:finalize") && (
                <FinalizationPanel
                  key={`${index.actor}:${projectId}`}
                  projectId={projectId}
                  ready={
                    project.progress.total > 0 &&
                    approved === project.progress.total &&
                    !project.project.finalized_version_id
                  }
                  onChanged={workspace.changed}
                />
              )}
              {!task && can("production:manage") && (
                <TemplateEditor
                  key={`${projectId}:${String(project.template?.revision)}`}
                  project={project}
                  onChanged={workspace.changed}
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
