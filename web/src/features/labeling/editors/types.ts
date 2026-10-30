import type { components } from "../../../api/generated";

export type AnnotationRecord = components["schemas"]["AnnotationRecord"];
export type AnnotationBox = components["schemas"]["AnnotationBox"];
export type AnnotationPolygon = components["schemas"]["AnnotationPolygon"];
export type AnnotationSpan = components["schemas"]["AnnotationSpan"];
export type ProductionLabel = components["schemas"]["ProductionLabel"];
export type ProductionTemplate = components["schemas"]["ProductionTemplate"];
/** Ask the editors to select one object; every request is a new object, even for the same target. */
export type LocateRequest = components["schemas"]["ObjectRef"];
export type Attributes = NonNullable<AnnotationRecord["attributes"]>;
export interface Point {
  x: number;
  y: number;
}
export interface EditorProps {
  value: AnnotationRecord;
  onChange: (value: AnnotationRecord) => void;
  labels: readonly ProductionLabel[];
  template: ProductionTemplate;
  mediaUrl?: string;
  thumbnailUrl?: string;
  text?: string;
  readOnly?: boolean;
  /** Show raw attribute JSON behind "Advanced" (project managers); defaults to true. */
  advancedAttributes?: boolean;
  /** Select the object a reviewer asked to locate. */
  locate?: LocateRequest | null;
}
