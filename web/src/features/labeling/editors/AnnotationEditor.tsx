import { BboxEditor } from "./BboxEditor";
import { ClassificationEditor } from "./ClassificationEditor";
import { PolygonEditor } from "./PolygonEditor";
import { SpanEditor } from "./SpanEditor";
import "./editors.css";

import type { EditorProps } from "./types";

export function AnnotationEditor(props: EditorProps) {
  const configured = props.template.component_config?.components;
  const components = [
    ...new Set(
      Array.isArray(configured) && configured.length
        ? configured.filter((item): item is string => typeof item === "string")
        : [props.template.annotation_type],
    ),
  ];
  return (
    <div className="wb-annotation-editor">
      {components.map((component) => {
        if (component === "box" || component === "bbox")
          return <BboxEditor key={component} {...props} />;
        if (component === "classification")
          return <ClassificationEditor key={component} {...props} />;
        if (component === "polygon")
          return <PolygonEditor key={component} {...props} />;
        if (component === "text_span" || component === "span")
          return <SpanEditor key={component} {...props} />;
        return null;
      })}
    </div>
  );
}
