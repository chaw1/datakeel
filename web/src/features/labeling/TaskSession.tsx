import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { TaskAiNotes } from "./ai/TaskAiNotes";
import { AnnotationEditor } from "./editors/AnnotationEditor";
import { DetailsSlotContext } from "./editors/editorContext";
import {
  allowed,
  annotatedBy,
  defaultTemplate,
  initialAnnotation,
  reworkIssues,
  startsFromScratch,
  taskEditable,
} from "./model";
import { SessionStatus } from "./SessionStatus";
import { TaskDrawer } from "./TaskDrawer";
import { TaskReview } from "./TaskReview";
import { TaskToolbar } from "./TaskToolbar";
import { exportDraft, TaskWatchNotice } from "./TaskWatchNotice";
import { useTaskActions } from "./useTaskActions";
import { useTaskKeyboard } from "./useTaskKeyboard";
import { useTaskSessionData } from "./useTaskSessionData";
import { useTaskWatch } from "./useTaskWatch";

import type { LocateRequest } from "./editors/types";
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
  const [locate, setLocate] = useState<LocateRequest | null>(null);
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
  const template = project.template ?? defaultTemplate;
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
  const returned = useRef<() => void>(() => undefined);
  const actions = useTaskActions({
    task,
    project,
    data,
    editable,
    reviewable,
    canSync,
    isIdentityVerified,
    onChanged,
    onReturned: () => {
      returned.current();
    },
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
    leaseMinutes: project.project.lease_minutes,
    onLost: () => {
      setLocked(true);
    },
  });
  useLayoutEffect(() => {
    returned.current = watch.notifyReturned;
  });
  const root = useRef<HTMLDivElement>(null);
  useTaskKeyboard(root, {
    editable: editable && !busy,
    // Once the task is taken back, Ctrl+S and Ctrl+Enter have nothing left to send.
    save: () => {
      if (!locked) void session.flush();
    },
    submit: () => {
      if (!locked) void perform("submit");
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
        {!locked && (
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
        )}
        <SessionStatus session={session} error={error} locked={locked} />
        <TaskWatchNotice
          {...watch}
          onRenew={() => {
            void watch.renew();
          }}
          locked={locked}
          issues={reworkIssues(snapshot)}
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
        {retry && !locked && (
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
              template={template}
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
              locate={locate}
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
          <TaskAiNotes
            task={snapshot}
            personal={personal}
            reviewable={reviewable}
            scratch={startsFromScratch(snapshot, personal)}
            passThrough={project.confidence_thresholds?.pass_through !== false}
            revisionId={session.revisionId}
            onUseDraft={
              editable && !busy && !session.dirty
                ? () => {
                    session.edit(initialAnnotation(snapshot, actor, template));
                  }
                : undefined
            }
            onLocate={setLocate}
          />
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
