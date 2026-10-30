import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { getTaskWorkbench } from "../../api/production";
import { useI18n } from "../../i18n/useI18n";

import { actionDetails, mutateProduction } from "./actions";
import { AnnotationEditor } from "./editors/AnnotationEditor";
import { DetailsSlotContext } from "./editors/editorContext";
import {
  allowed,
  defaultTemplate,
  initialAnnotation,
  taskEditable,
} from "./model";
import { savedRevision } from "./savedRevision";
import { useAnnotationSession } from "./session/useAnnotationSession";
import { SessionStatus } from "./SessionStatus";
import { TaskDrawer } from "./TaskDrawer";
import { TaskReview } from "./TaskReview";
import { TaskToolbar } from "./TaskToolbar";
import { useTaskKeyboard } from "./useTaskKeyboard";

import type {
  AnnotationRecord,
  ProjectWorkbench,
  TaskWorkbench,
} from "../../api/production";

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
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [help, setHelp] = useState(false);
  const [issue, setIssue] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [detailsSlot, setDetailsSlot] = useState<HTMLDivElement | null>(null);
  const [snapshot, setSnapshot] = useState(task);
  const snapshotRef = useRef(task);
  const acceptSnapshot = useCallback(
    (next: TaskWorkbench) => {
      snapshotRef.current = next;
      setSnapshot(next);
      onSnapshot(next);
    },
    [onSnapshot],
  );
  const personal = project.project.workflow_tier === "personal";
  const editable =
    allowed(project.effective_scopes, "production:annotate") &&
    taskEditable(snapshot, actor, personal);
  const reviewable =
    !personal &&
    allowed(project.effective_scopes, "production:review") &&
    ["submitted", "in_review"].includes(snapshot.task.state) &&
    !snapshot.assignments.some(
      (assignment) =>
        assignment.active &&
        assignment.stage === "review" &&
        assignment.actor !== actor,
    );
  const reads = useRef(0);
  const refreshSnapshot = useCallback(async () => {
    const request = ++reads.current;
    const fresh = await getTaskWorkbench(task.task.id);
    if (request === reads.current) acceptSnapshot(fresh);
    return fresh;
  }, [task.task.id, acceptSnapshot]);
  const load = useCallback(async () => {
    const fresh = await refreshSnapshot();
    return {
      annotation: initialAnnotation(fresh, actor),
      revisionId: fresh.task.latest_revision_id ?? null,
    };
  }, [actor, refreshSnapshot]);
  const save = useCallback(
    async (annotation: AnnotationRecord, previousRevisionId: string | null) => {
      if (!canSync || isIdentityVerified?.() === false)
        throw new ApiError(503, t("wbOffline"));
      const run = await mutateProduction("save_revision", {
        task_id: task.task.id,
        previous_revision_id: previousRevisionId,
        annotation,
      });
      const saved = savedRevision(snapshotRef.current, actionDetails(run));
      if (!saved) throw new Error(t("wbSaveError"));
      reads.current++;
      acceptSnapshot(saved.task);
      onChanged();
      void refreshSnapshot().catch(() => undefined);
      return {
        annotation: saved.revision.annotation,
        revisionId: saved.revision.id,
      };
    },
    [
      task.task.id,
      onChanged,
      t,
      canSync,
      isIdentityVerified,
      refreshSnapshot,
      acceptSnapshot,
    ],
  );
  const session = useAnnotationSession({
    key: `${actor}:${project.project.id}:${task.task.id}`,
    initial: {
      annotation: initialAnnotation(task, actor),
      revisionId: task.task.latest_revision_id ?? null,
    },
    save,
    reload: load,
  });
  const { flush, dirty, reload } = session;
  const wasVerified = useRef(canSync);
  useEffect(() => {
    if (canSync && !wasVerified.current) {
      if (dirty) void flush();
      else void reload();
    }
    wasVerified.current = canSync;
  }, [canSync, flush, dirty, reload]);
  useEffect(() => {
    registerGuard(flush);
    return () => {
      registerGuard(null);
    };
  }, [flush, registerGuard]);
  async function perform(operation: "submit" | "approve" | "rework") {
    if (busy || (operation === "submit" ? !editable : !reviewable)) return;
    if (!canSync || isIdentityVerified?.() === false) {
      setError(t("wbOffline"));
      return;
    }
    if (operation === "rework" && !issue.trim()) {
      setError(t("wbReviewRequired"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (!(await flush())) return;
      const fresh = await getTaskWorkbench(task.task.id);
      if (isIdentityVerified?.() === false) {
        setError(t("wbOffline"));
        return;
      }
      if (
        operation !== "submit" &&
        (fresh.task.latest_revision_id ?? null) !== session.revisionId
      ) {
        await reload();
        setError(t("wbReviewChanged"));
        return;
      }
      await mutateProduction(
        operation === "submit" ? "submit_task" : "review_task",
        {
          task_id: task.task.id,
          ...(operation === "submit"
            ? {}
            : {
                revision_id: session.revisionId ?? "",
                decision: operation,
                issues: operation === "rework" ? [issue.trim()] : [],
              }),
        },
      );
      await refreshSnapshot();
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("wbSaveError"));
    } finally {
      setBusy(false);
    }
  }
  const root = useRef<HTMLDivElement>(null);
  useTaskKeyboard(root, {
    editable: editable && !busy,
    save: () => {
      void flush();
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
              issue={issue}
              busy={busy}
              onIssue={setIssue}
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
