import type {
  EffectiveScopes,
  ProductionTask,
  TaskWorkbench,
  AnnotationRecord,
  ProductionTemplate,
} from "../../api/production";
import type { MessageKey } from "../../i18n/en";

export type WorkbenchView = "data" | "tasks" | "reviews" | "cockpit";
export function allowed(scopes: EffectiveScopes, scope: string) {
  return (
    scopes.zero_users ||
    scopes.scopes.includes("*") ||
    scopes.scopes.includes(scope)
  );
}
export const stateMessages: Record<ProductionTask["state"], MessageKey> = {
  pending: "wbPending",
  in_progress: "wbInProgress",
  submitted: "wbSubmitted",
  in_review: "wbInReview",
  approved: "wbApproved",
  finalized: "wbFinalized",
};
export function initialAnnotation(
  task: TaskWorkbench,
  actor: string,
): AnnotationRecord {
  const latest = task.revisions.find(
    (revision) => revision.id === task.task.latest_revision_id,
  );
  return {
    ...(latest?.annotation ?? {
      sample_id: task.task.sample_id,
      image_width: task.sample.image_width,
      image_height: task.sample.image_height,
      text_length: task.sample.text
        ? Array.from(task.sample.text).length
        : null,
    }),
    annotator_id: actor,
    image_width: latest?.annotation.image_width ?? task.sample.image_width,
    image_height: latest?.annotation.image_height ?? task.sample.image_height,
    text_length:
      latest?.annotation.text_length ??
      (task.sample.text == null ? null : Array.from(task.sample.text).length),
  };
}
export const defaultTemplate: ProductionTemplate = {
  id: "default-box",
  name: "Box",
  annotation_type: "box",
  component_config: {},
  validation_rules: {},
  revision: 1,
  archived: false,
};
export function taskEditable(
  task: TaskWorkbench,
  actor: string,
  personal: boolean,
) {
  return (
    ["pending", "in_progress"].includes(task.task.state) &&
    (personal ||
      task.assignments.some(
        (assignment) =>
          assignment.active &&
          assignment.stage === "annotation" &&
          assignment.actor === actor,
      ))
  );
}
