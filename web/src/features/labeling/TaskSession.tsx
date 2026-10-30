import { useEffect, useRef, useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { AnnotationEditor } from "./editors/AnnotationEditor";
import { DetailsSlotContext } from "./editors/editorContext";
import { allowed, annotatedBy, defaultTemplate, taskEditable } from "./model";
import { SessionStatus } from "./SessionStatus";
import { TaskDrawer } from "./TaskDrawer";
import { TaskReview } from "./TaskReview";
import { TaskToolbar } from "./TaskToolbar";
import { exportDraft, TaskWatchNotice } from "./TaskWatchNotice";
import { useTaskActions } from "./useTaskActions";
import { useTaskKeyboard } from "./useTaskKeyboard";
import { useTaskSessionData } from "./useTaskSessionData";
import { useTaskWatch } from "./useTaskWatch";

import type { ProjectWorkbench, TaskWorkbench } from "../../api/production";

export function TaskSession({
  task,
  project,
  actor,
  canSync,
  isIdentityVerified,
  onNavigate,
  navigation = { previous: true, next: true },
  notice = "",
  onChanged,
  onSnapshot,
  registerGuard,
}: {
  task: TaskWorkbench;
  project: ProjectWorkbench;
  actor: string;
  canSync: boolean;
  isIdentityVerified?: () => boolean;
  onNavigate: (direction: -1 | 0 | 1) => void;
  navigation?: { previous: boolean; next: boolean };
  notice?: string;
  onChanged: () => void;
  onSnapshot: (task: TaskWorkbench) => void;
  registerGuard: (guard: (() => Promise<boolean>) | null) => void;
}) {
  const { t } = useI18n();
  const [help, setHelp] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [detailsSlot, setDetailsSlot] = useState<HTMLDivElement | null>(null);
  const [locked, setLocked] = useState(false);
  const data = useTaskSessionData({
    task,
    project,
    actor,
    canSync,
    isIdentityVerified,
    onChanged,
    onSnapshot,
    registerGuard,
    onLeaseLost: () => {
      setLocked(true);
    },
    leaveFreely: locked,
  });
  const { snapshot, session } = data;
  const personal = project.project.workflow_tier === "personal";
  const editable =
    allowed(project.effective_scopes, "production:annotate") &&
    taskEditable(snapshot, actor, personal) &&
    !locked;
  const reviewable =
    !personal &&
    allowed(project.effective_scopes, "production:review") &&
    ["submitted", "in_review"].includes(snapshot.task.state) &&
    !annotatedBy(snapshot, actor) &&
    !snapshot.assignments.some(
      (assignment) =>
        assignment.active &&
        assignment.stage === "review" &&
        assignment.actor !== actor,
    );
  const actions = useTaskActions({
    task,
    project,
    data,
    editable,
    reviewable,
    canSync,
    isIdentityVerified,
    onChanged,
  });
  const { perform, busy, error, retry } = actions;
  const watch = useTaskWatch({
    taskId: task.task.id,
    actor,
    team: project.project.workflow_tier === "team",
    state: snapshot.task.state,
    revisionId: session.revisionId,
    quiet: busy || ["saving", "pending"].includes(session.status),
    locked,
    onLost: () => {
      setLocked(true);
    },
  });
  const root = useRef<HTMLDivElement>(null);
  useTaskKeyboard(root, {
    editable: editable && !busy,
    save: () => {
      void session.flush();
    },
    submit: () => {
      void perform("submit");
    },
    undo: session.undo,
    redo: session.redo,
    navigate: onNavigate,
    help: () => {
      setHelp(!help);
    },
  });
  useEffect(() => {
    const target = root.current?.querySelector<HTMLElement>(
      ".wb-canvas,input[type=radio],input[type=checkbox],.wb-span-source",
    );
    (target ?? root.current)?.focus({ preventScroll: true });
  }, []);
  return (
    <div
      ref={root}
      tabIndex={-1}
      role="region"
      className="wb-session"
      aria-label={t("wbNav")}
      data-task-id={task.task.id}
    >
      <div className="wb-operation-bar">
        <h2 className="wb-task-name">{task.sample.name}</h2>
        <TaskToolbar
          editable={editable}
          busy={busy}
          personal={personal}
          session={session}
          onNavigate={onNavigate}
          navigation={navigation}
          notice={notice}
          onSubmit={() => {
            void perform("submit");
          }}
          help={help}
          setHelp={setHelp}
        />
        <SessionStatus session={session} error={error} />
        <TaskWatchNotice
          {...watch}
          onRenew={() => {
            void watch.renew();
          }}
          locked={locked}
          onExport={() => {
            exportDraft(session.annotation, task.sample.name);
          }}
          onReload={() => {
            watch.dismiss();
            void data.refreshSnapshot().then(() => {
              if (!session.dirty) void session.reload();
            });
          }}
          onBack={() => {
            // The list shown before may be stale: this task changed hands or state.
            onChanged();
            onNavigate(0);
          }}
        />
        {retry && (
          <button
            type="button"
            className="wb-retry-action"
            disabled={busy}
            onClick={() => {
              void perform(retry);
            }}
          >
            {t("wbRedoAction")}
          </button>
        )}
      </div>
      <div
        className="wb-work-area"
        data-drawer={drawerOpen ? "open" : "closed"}
      >
        <div className="wb-editor">
          <DetailsSlotContext value={detailsSlot}>
            <AnnotationEditor
              value={session.annotation}
              onChange={session.edit}
              labels={project.label_set.labels}
              template={project.template ?? defaultTemplate}
              mediaUrl={task.sample.content_url}
              thumbnailUrl={
                (task.sample.image_width ?? 0) > 3000 ||
                (task.sample.image_height ?? 0) > 2000
                  ? (task.sample.thumbnail_url ?? undefined)
                  : undefined
              }
              text={task.sample.text ?? undefined}
              readOnly={!editable || busy}
              advancedAttributes={allowed(
                project.effective_scopes,
                "production:manage",
              )}
            />
          </DetailsSlotContext>
        </div>
        <TaskDrawer
          task={snapshot}
          project={project}
          open={drawerOpen}
          onToggle={() => {
            setDrawerOpen(!drawerOpen);
          }}
          detailsRef={setDetailsSlot}
        >
          {!editable && <p className="muted">{t("wbReadOnly")}</p>}
          {reviewable && (
            <TaskReview
              issue={actions.issue}
              busy={busy}
              onIssue={actions.setIssue}
              onReview={(decision) => {
                void perform(decision);
              }}
            />
          )}
        </TaskDrawer>
      </div>
    </div>
  );
}
