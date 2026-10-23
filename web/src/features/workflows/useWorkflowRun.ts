import { useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { streamWorkflow } from "../../api/workflows";
import { useResource } from "../../lib/useResource";

import { workflowHref } from "./labels";

import type {
  WorkflowRun,
  WorkflowStart,
  WorkflowResume,
} from "../../api/workflows";

export function useWorkflowRun(initialId: string, onComplete: () => void) {
  const [id, setId] = useState(initialId);
  const saved = useResource<WorkflowRun>(
    id ? `/api/workflows/runs/${encodeURIComponent(id)}` : null,
  );
  const [snapshot, setSnapshot] = useState<WorkflowRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [interrupted, setInterrupted] = useState(false);
  const request = useRef<AbortController | null>(null);
  const executing = useRef(false);
  useEffect(
    () => () => {
      request.current?.abort();
    },
    [],
  );
  async function execute(path: string, body: WorkflowStart | WorkflowResume) {
    if (executing.current) return;
    executing.current = true;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setFailure("");
    setInterrupted(false);
    try {
      await streamWorkflow(
        path,
        body,
        (event) => {
          if (controller.signal.aborted) return;
          setSnapshot(event.run);
          setId(event.run.id);
          window.history.replaceState(
            null,
            "",
            `/${workflowHref(event.run.id)}`,
          );
        },
        controller.signal,
      );
    } catch (reason) {
      if (!controller.signal.aborted) {
        setInterrupted(!(reason instanceof ApiError));
        setFailure(reason instanceof Error ? reason.message : String(reason));
      }
    } finally {
      executing.current = false;
      if (!controller.signal.aborted) {
        setBusy(false);
        onComplete();
      }
    }
  }
  const value = snapshot ?? saved.value;
  return {
    value,
    busy,
    loading: saved.loading && !snapshot,
    error: failure || saved.error,
    interrupted,
    reload: () => {
      setSnapshot(null);
      setFailure("");
      setInterrupted(false);
      saved.reload();
    },
    start: (workflowId: string, inputs: WorkflowStart["inputs"]) => {
      if (executing.current) return Promise.resolve();
      setSnapshot(null);
      setId("");
      return execute(`/api/workflows/${encodeURIComponent(workflowId)}/runs`, {
        inputs,
        idempotency_key: crypto.randomUUID(),
      });
    },
    resume: () =>
      value?.pending_plan_id
        ? execute(
            `/api/workflows/runs/${encodeURIComponent(value.id)}/resume`,
            {
              plan_id: value.pending_plan_id,
              idempotency_key: crypto.randomUUID(),
            },
          )
        : Promise.resolve(),
  };
}
