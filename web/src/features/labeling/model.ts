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
export const viewMessages: Record<WorkbenchView, MessageKey> = {
  data: "wbMyData",
  tasks: "wbMyTasks",
  reviews: "wbReviewQueue",
  cockpit: "wbCockpit",
};
/** Role views the navigation offers, in display order; the first is the landing view. */
export function workbenchViews(
  personal: boolean,
  scopes: EffectiveScopes,
): WorkbenchView[] {
  if (personal) return ["data"];
  const views: WorkbenchView[] = [];
  if (allowed(scopes, "production:annotate")) views.push("tasks");
  if (allowed(scopes, "production:review")) views.push("reviews");
  if (
    allowed(scopes, "production:manage") ||
    allowed(scopes, "production:finalize")
  )
    views.push("cockpit");
  return views;
}
/** Keep a usable view; a restored or stale one outside the navigation becomes the first allowed. */
export function correctedView(
  view: WorkbenchView,
  personal: boolean,
  scopes: EffectiveScopes,
): WorkbenchView {
  const views = workbenchViews(personal, scopes);
  return views.includes(view) ? view : (views[0] ?? "cockpit");
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
  attributes: [],
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
/** Team tier: whoever annotated a task in any round never reviews it; the server refuses it too. */
export function annotatedBy(task: TaskWorkbench, actor: string) {
  return (
    task.task.annotator_id === actor ||
    task.revisions.some(
      (revision) => revision.actor === actor && revision.source === "human",
    ) ||
    task.assignments.some(
      (assignment) =>
        assignment.stage === "annotation" && assignment.actor === actor,
    )
  );
}
