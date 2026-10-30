import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { getTaskStatus } from "../../api/production";
import { useI18n } from "../../i18n/useI18n";

import { actionMessage, actionProblem } from "./actionErrors";
import { mutateProduction } from "./actions";

import type { ProductionTask, WorkbenchTaskStatus } from "../../api/production";

type TaskState = ProductionTask["state"];

/** Status reads every 5 s keep "changed elsewhere" notices well inside the 10 s budget. */
export const WATCH_INTERVAL_MS = 5_000;
/** Team leases are renewed every 2 minutes while the task is open, or sooner for short leases. */
export const HEARTBEAT_INTERVAL_MS = 120_000;

/** Renew at least three times per lease: min(2 minutes, lease length / 3). */
export function heartbeatInterval(leaseSeconds: number | null) {
  return leaseSeconds && leaseSeconds > 0
    ? Math.min(HEARTBEAT_INTERVAL_MS, (leaseSeconds * 1000) / 3)
    : HEARTBEAT_INTERVAL_MS;
}

export type TaskChange =
  | { kind: "returned" }
  | { kind: "state"; state: TaskState }
  | { kind: "edited" };

/**
 * Watch the open task: renew the caller's team lease, count it down, and notice when the
 * task is returned, reclaimed, expired or edited elsewhere. Local drafts are never touched.
 */
export function useTaskWatch({
  taskId,
  actor,
  team,
  state,
  revisionId,
  quiet,
  locked,
  leaseMinutes,
  onLost,
}: {
  taskId: string;
  actor: string;
  team: boolean;
  /** Task state and revision this page last showed. */
  state: TaskState;
  revisionId: string | null;
  /** True while this page is saving or acting itself, so its own writes are not "changes". */
  quiet: boolean;
  locked: boolean;
  /** The project's configured lease; replaced by what the server grants on each renewal. */
  leaseMinutes?: number;
  onLost: () => void;
}) {
  const { t } = useI18n();
  const [deadline, setDeadline] = useState<number | null>(null);
  const [stage, setStage] = useState<"annotation" | "review" | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [change, setChange] = useState<TaskChange | null>(null);
  const [renewals, setRenewals] = useState(0);
  const [granted, setGranted] = useState<number | null>(null);
  const [heartbeatError, setHeartbeatError] = useState("");
  const shown = useRef({ state, revisionId, quiet, locked });
  useLayoutEffect(() => {
    shown.current = { state, revisionId, quiet, locked };
  });
  const known = useRef<Set<string> | null>(null);
  const lost = useRef(onLost);
  useLayoutEffect(() => {
    lost.current = onLost;
  });
  const accept = useCallback(
    (status: WorkbenchTaskStatus) => {
      const view = shown.current;
      const mine = status.leases.find((lease) => lease.actor === actor);
      setStage(mine?.enforced ? mine.stage : null);
      setDeadline(
        mine?.enforced ? Date.now() + mine.seconds_remaining * 1000 : null,
      );
      const releases = status.releases.filter(
        (release) => release.actor === actor,
      );
      if (known.current === null)
        known.current = new Set(releases.map((item) => item.assignment_id));
      else if (releases.some((item) => !known.current?.has(item.assignment_id)))
        lost.current();
      if (view.quiet || view.locked) return;
      if (status.task.state !== view.state)
        setChange(
          ["submitted", "in_review"].includes(view.state) &&
            ["pending", "in_progress"].includes(status.task.state)
            ? { kind: "returned" }
            : { kind: "state", state: status.task.state },
        );
      else if ((status.task.latest_revision_id ?? null) !== view.revisionId)
        setChange({ kind: "edited" });
    },
    [actor],
  );
  const read = useCallback(async () => {
    const status = await getTaskStatus(taskId);
    accept(status);
    return status;
  }, [accept, taskId]);
  useEffect(() => {
    const poll = () => {
      void read().catch(() => undefined);
    };
    poll();
    const timer = setInterval(poll, WATCH_INTERVAL_MS);
    const visible = () => {
      if (document.visibilityState === "visible") poll();
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [read]);
  const renew = useCallback(async () => {
    if (!stage) return;
    try {
      await mutateProduction("heartbeat", { task_id: taskId, stage });
      setHeartbeatError("");
      setRenewals((count) => count + 1);
      const status = await read();
      // Just renewed, so the time left is the lease length the server grants.
      const mine = status.leases.find((lease) => lease.actor === actor);
      if (mine?.enforced) setGranted(mine.seconds_remaining);
    } catch (reason) {
      if (actionProblem(reason) === "lease") lost.current();
      else setHeartbeatError(actionMessage(reason, t, t("wbError")));
    }
  }, [actor, read, stage, t, taskId]);
  const renewing = useRef(renew);
  useLayoutEffect(() => {
    renewing.current = renew;
  });
  const cadence = heartbeatInterval(
    granted ?? (leaseMinutes ? leaseMinutes * 60 : null),
  );
  // Renew on open; restart only when the held lease changes.
  useEffect(() => {
    if (!team || !stage || locked) return;
    const first = setTimeout(() => {
      void renewing.current();
    }, 0);
    return () => {
      clearTimeout(first);
    };
  }, [team, stage, locked, taskId]);
  // Then renew every min(2 minutes, lease / 3), including while the tab is hidden.
  useEffect(() => {
    if (!team || !stage || locked) return;
    const timer = setInterval(() => {
      void renewing.current();
    }, cadence);
    return () => {
      clearInterval(timer);
    };
  }, [team, stage, locked, taskId, cadence]);
  useEffect(() => {
    if (deadline === null || locked) return;
    const timer = setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, [deadline, locked]);
  const remaining =
    deadline === null ? null : Math.max(0, Math.round((deadline - now) / 1000));
  useEffect(() => {
    if (remaining === 0 && !locked) lost.current();
  }, [remaining, locked]);
  return {
    remaining,
    renewals,
    heartbeatError,
    renew,
    change,
    dismiss: () => {
      setChange(null);
    },
    notifyReturned: () => {
      setChange({ kind: "returned" });
    },
  };
}
