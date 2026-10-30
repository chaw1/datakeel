import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { getTaskWorkbench } from "../../api/production";
import { useI18n } from "../../i18n/useI18n";

import { actionMessage, actionProblem } from "./actionErrors";
import { actionDetails, mutateProduction } from "./actions";
import { problemText } from "./attributeMessages";
import { attributeProblems } from "./editors/attributes";
import { defaultTemplate, initialAnnotation, startsFromScratch } from "./model";
import { savedRevision } from "./savedRevision";
import { useAnnotationSession } from "./session/useAnnotationSession";
import { countProblem } from "./templateContent";

import type {
  AnnotationRecord,
  ProjectWorkbench,
  TaskWorkbench,
} from "../../api/production";

/** The task snapshot, its autosaving annotation session and server reads/writes. */
export function useTaskSessionData({
  task,
  project,
  actor,
  canSync,
  isIdentityVerified,
  onChanged,
  onSnapshot,
  registerGuard,
  onLeaseLost,
  leaveFreely = false,
}: {
  task: TaskWorkbench;
  project: ProjectWorkbench;
  actor: string;
  canSync: boolean;
  isIdentityVerified?: () => boolean;
  onChanged: () => void;
  onSnapshot: (task: TaskWorkbench) => void;
  registerGuard: (guard: (() => Promise<boolean>) | null) => void;
  /** The server reports this person's lease expired or the task was reclaimed. */
  onLeaseLost?: () => void;
  /** The task was taken back: a save can never succeed, so leaving must not wait for one. */
  leaveFreely?: boolean;
}) {
  const { t, locale } = useI18n();
  const personal = project.project.workflow_tier === "personal";
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
  const reads = useRef(0);
  const refreshSnapshot = useCallback(async () => {
    const request = ++reads.current;
    const fresh = await getTaskWorkbench(task.task.id);
    if (request === reads.current) acceptSnapshot(fresh);
    return fresh;
  }, [task.task.id, acceptSnapshot]);
  const template = project.template ?? defaultTemplate;
  const load = useCallback(async () => {
    const fresh = await refreshSnapshot();
    return {
      annotation: initialAnnotation(
        fresh,
        actor,
        template,
        startsFromScratch(fresh, personal),
      ),
      revisionId: fresh.task.latest_revision_id ?? null,
    };
  }, [actor, refreshSnapshot, personal, template]);
  const save = useCallback(
    async (annotation: AnnotationRecord, previousRevisionId: string | null) => {
      if (!canSync || isIdentityVerified?.() === false)
        throw new ApiError(503, t("wbOffline"));
      const run = await mutateProduction("save_revision", {
        task_id: task.task.id,
        previous_revision_id: previousRevisionId,
        annotation,
      }).catch((reason: unknown) => {
        const problem = actionProblem(reason);
        if (problem === "lease") {
          onLeaseLost?.();
          // Not a 409: a reclaim is not a revision conflict to resolve by overwriting.
          throw new ApiError(403, t("wbLeaseLost"));
        }
        if (problem === "changed")
          throw new ApiError(409, actionMessage(reason, t));
        throw reason;
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
      onLeaseLost,
    ],
  );
  /** The server's own save rules, so the person reads them in their language: count, then attributes. */
  const validate = useCallback(
    (annotation: AnnotationRecord) => {
      const counted = countProblem(annotation, template, t);
      if (counted) return counted;
      const first = attributeProblems(annotation, template).at(0);
      return first ? problemText(first, t, locale) : "";
    },
    [template, t, locale],
  );
  const session = useAnnotationSession({
    key: `${actor}:${project.project.id}:${task.task.id}`,
    initial: {
      annotation: initialAnnotation(
        task,
        actor,
        template,
        startsFromScratch(task, personal),
      ),
      revisionId: task.task.latest_revision_id ?? null,
    },
    save,
    reload: load,
    validate,
  });
  const { flush, dirty, reload } = session;
  const { annotation: shown, revisionId: shownRevision } = session;
  /**
   * The server only takes a submission over the person's own revision. While the head is
   * still a model draft, save what they see as theirs first: the empty start over a low
   * draft (never the hidden draft), or a medium or personal draft confirmed unchanged.
   */
  const settleModelDraft = useCallback(async () => {
    const current = snapshotRef.current;
    const head = current.revisions.find(
      (revision) => revision.id === current.task.latest_revision_id,
    );
    if (dirty || head?.source !== "model" || head.id !== shownRevision)
      return true;
    await save(shown, shownRevision);
    return reload();
  }, [dirty, shownRevision, save, shown, reload]);
  const wasVerified = useRef(canSync);
  useEffect(() => {
    if (canSync && !wasVerified.current) {
      if (dirty) void flush();
      else void reload();
    }
    wasVerified.current = canSync;
  }, [canSync, flush, dirty, reload]);
  useEffect(() => {
    registerGuard(leaveFreely ? null : flush);
    return () => {
      registerGuard(null);
    };
  }, [flush, registerGuard, leaveFreely]);
  return { snapshot, session, refreshSnapshot, validate, settleModelDraft };
}
