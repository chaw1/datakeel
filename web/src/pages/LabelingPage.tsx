import { useRef, useState } from "react";

import { mutateProduction, actionDetails } from "../features/labeling/actions";
import { FinalizationPanel } from "../features/labeling/FinalizationPanel";
import { allowed } from "../features/labeling/model";
import { ModuleBar } from "../features/labeling/ModuleBar";
import { ProjectCockpit } from "../features/labeling/ProjectCockpit";
import { TaskList } from "../features/labeling/TaskList";
import { TaskSearch } from "../features/labeling/TaskSearch";
import { TaskSession } from "../features/labeling/TaskSession";
import { TemplateEditor } from "../features/labeling/TemplateEditor";
import { useLabelingWorkspace } from "../features/labeling/useLabelingWorkspace";
import { useViewportFill } from "../features/labeling/useViewportFill";
import { useI18n } from "../i18n/useI18n";

import "../features/labeling/workbench.css";

export function LabelingPage({ params }: { params: URLSearchParams }) {
  const { t } = useI18n();
  const workspace = useLabelingWorkspace(params);
  const { index, project, task, projectId, view, error, busy } = workspace;
  const page = useRef<HTMLDivElement>(null);
  const focus = !!task && !!project;
  const height = useViewportFill(page, focus);
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
  return (
    <div
      ref={page}
      className="wb-page"
      data-focus={focus ? "true" : undefined}
      style={height === undefined ? undefined : { height }}
    >
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
          <ModuleBar workspace={workspace} />
          {project && (
            <>
              {busy && (
                <p role="status" className="wb-busy">
                  {t("wbLoading")}
                </p>
              )}
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
                  navigation={workspace.navigation}
                  notice={
                    workspace.notice === "last"
                      ? t("wbNoNextTask")
                      : workspace.notice === "first"
                        ? t("wbNoPreviousTask")
                        : ""
                  }
                  onChanged={() => {
                    workspace.cache.invalidate(task.task.id);
                    workspace.changed();
                  }}
                  onSnapshot={workspace.receiveTask}
                  registerGuard={workspace.registerGuard}
                />
              ) : view === "cockpit" ? (
                <ProjectCockpit
                  data={project}
                  can={can}
                  onChanged={workspace.changed}
                />
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
                  <TaskSearch
                    value={workspace.search}
                    onSearch={workspace.searchTasks}
                  />
                  <TaskList
                    tasks={project.tasks}
                    samples={project.task_samples}
                    risks={project.task_risks}
                    onOpen={(item) => {
                      void workspace.open(item.id);
                    }}
                  />
                  <div className="wb-pagination">
                    <button
                      type="button"
                      disabled={workspace.page === 0}
                      onClick={() => {
                        void workspace.paginate(-1);
                      }}
                    >
                      {t("wbPageBack")}
                    </button>
                    <span>{t("wbPage", { page: workspace.page + 1 })}</span>
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
                  summary={{
                    tasks: approved,
                    blocked: project.progress.total - approved,
                    datasetId: project.project.dataset_id,
                    versionId: project.project.version_id,
                  }}
                  onChanged={workspace.changed}
                />
              )}
              {!task && can("production:manage") && (
                <TemplateEditor
                  key={`${projectId}:${String((project.latest_template ?? project.template)?.revision)}`}
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
