import type { components } from "../../api/generated";
import type { TaskWorkbench } from "../../api/production";

type Revision = components["schemas"]["AnnotationRevision"];

/** Decode the generated revision receipt before publishing a durable saved snapshot. */
export function savedRevision(
  previous: TaskWorkbench,
  payload: unknown,
): { task: TaskWorkbench; revision: Revision } | null {
  if (
    !payload ||
    typeof payload !== "object" ||
    !("id" in payload) ||
    typeof payload.id !== "string" ||
    !("task_id" in payload) ||
    payload.task_id !== previous.task.id ||
    !("annotation" in payload) ||
    !payload.annotation ||
    typeof payload.annotation !== "object" ||
    !("sample_id" in payload.annotation) ||
    payload.annotation.sample_id !== previous.task.sample_id ||
    !("annotator_id" in payload.annotation) ||
    typeof payload.annotation.annotator_id !== "string" ||
    !("actor" in payload) ||
    typeof payload.actor !== "string" ||
    !("created_at" in payload) ||
    typeof payload.created_at !== "string" ||
    !("source" in payload) ||
    !["human", "model"].includes(String(payload.source))
  )
    return null;
  const revision = payload as Revision;
  return {
    revision,
    task: {
      ...previous,
      task: {
        ...previous.task,
        state: "in_progress",
        latest_revision_id: revision.id,
        annotator_id: revision.actor,
        confidence: revision.confidence,
      },
      revisions: [
        ...previous.revisions.filter((item) => item.id !== revision.id),
        revision,
      ],
    },
  };
}
