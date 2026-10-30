import { useI18n } from "../../../i18n/useI18n";

import { AttributeForm } from "./AttributeForm";
import { attributeFields, withDefaults } from "./attributes";
import { BboxEditor } from "./BboxEditor";
import { ClassificationEditor } from "./ClassificationEditor";
import { EditorDetails } from "./EditorDetails";
import { PolygonEditor } from "./PolygonEditor";
import { SpanEditor } from "./SpanEditor";
import "./editors.css";

import type { AnnotationRecord, EditorProps } from "./types";

export function AnnotationEditor(props: EditorProps) {
  const { t } = useI18n();
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
  const recordFields = attributeFields(props.template, "record");
  // Raw record JSON stays where it was before forms existed: beside classification.
  const advanced =
    (props.advancedAttributes ?? true) && components.includes("classification");
  // Any edit also fills configured record defaults, so they are saved with the first change.
  const change = (next: AnnotationRecord) => {
    props.onChange(
      recordFields.some((field) => field.default != null)
        ? { ...next, attributes: withDefaults(next.attributes, recordFields) }
        : next,
    );
  };
  const editorProps = { ...props, onChange: change };
  return (
    <div className="wb-annotation-editor">
      {components.map((component) => {
        if (component === "box" || component === "bbox")
          return <BboxEditor key={component} {...editorProps} />;
        if (component === "classification")
          // Beside an image, classification sits in the drawer so the canvas keeps its height.
          return onImage ? (
            <EditorDetails key={component} label={props.template.name}>
              <ClassificationEditor {...editorProps} />
            </EditorDetails>
          ) : (
            <ClassificationEditor key={component} {...editorProps} />
          );
        if (component === "polygon")
          return <PolygonEditor key={component} {...editorProps} />;
        if (component === "text_span" || component === "span")
          return <SpanEditor key={component} {...editorProps} />;
        return null;
      })}
      {(recordFields.length > 0 || advanced) && (
        <EditorDetails label={t("wbRecordAttributes")}>
          <AttributeForm
            label={t("wbRecordAttributes")}
            fields={recordFields}
            value={props.value.attributes}
            readOnly={props.readOnly}
            advanced={advanced}
            onChange={(attributes) => {
              change({ ...props.value, attributes });
            }}
          />
        </EditorDetails>
      )}
    </div>
  );
}
