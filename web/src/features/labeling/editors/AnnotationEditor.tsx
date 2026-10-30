import { BboxEditor } from "./BboxEditor";
import { ClassificationEditor } from "./ClassificationEditor";
import { EditorDetails } from "./EditorDetails";
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
  const onImage = components.some((item) =>
    ["box", "bbox", "polygon"].includes(item),
  );
  return (
    <div className="wb-annotation-editor">
      {components.map((component) => {
        if (component === "box" || component === "bbox")
          return <BboxEditor key={component} {...props} />;
        if (component === "classification")
          // Beside an image, classification sits in the drawer so the canvas keeps its height.
          return onImage ? (
            <EditorDetails key={component} label={props.template.name}>
              <ClassificationEditor {...props} />
            </EditorDetails>
          ) : (
            <ClassificationEditor key={component} {...props} />
          );
        if (component === "polygon")
          return <PolygonEditor key={component} {...props} />;
        if (component === "text_span" || component === "span")
          return <SpanEditor key={component} {...props} />;
        return null;
      })}
    </div>
  );
}
