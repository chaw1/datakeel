import type { components } from "../../../api/generated";

export type AnnotationRecord = components["schemas"]["AnnotationRecord"];
export type AnnotationBox = components["schemas"]["AnnotationBox"];
export type AnnotationPolygon = components["schemas"]["AnnotationPolygon"];
export type AnnotationSpan = components["schemas"]["AnnotationSpan"];
export type ProductionLabel = components["schemas"]["ProductionLabel"];
export type ProductionTemplate = components["schemas"]["ProductionTemplate"];
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
}
