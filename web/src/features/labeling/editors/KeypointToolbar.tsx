import { useI18n } from "../../../i18n/useI18n";

import { LabelPicker } from "./LabelPicker";

import type {
  AnnotationSkeleton,
  ProductionLabel,
  ProductionTemplate,
} from "./types";

export function KeypointToolbar({
  labels,
  template,
  skeletons,
  selected,
  category,
  readOnly,
  onSelect,
  onAdd,
  onDelete,
  onLabel,
}: {
  labels: readonly ProductionLabel[];
  template: ProductionTemplate;
  skeletons: readonly AnnotationSkeleton[];
  selected: number;
  category: string;
  readOnly?: boolean;
  onSelect: (index: number) => void;
  onAdd: () => void;
  onDelete: () => void;
  onLabel: (category: string) => void;
}) {
  const { t } = useI18n();
  return (
    <>
      <label>
        {t("wbKeypointInstance")}
        <select
          value={selected < 0 ? "" : selected}
          disabled={!skeletons.length}
          onChange={(event) => {
            onSelect(Number(event.target.value));
          }}
          onBlur={(event) => {
            onSelect(Number(event.target.value));
          }}
        >
          {!skeletons.length && <option value="">{t("wbEditorNone")}</option>}
          {skeletons.map((skeleton, index) => (
            <option key={index} value={index}>
              {t("wbEditorAnnotationName", {
                label:
                  labels.find((label) => label.id === skeleton.category)
                    ?.name ?? skeleton.category,
                index: index + 1,
              })}
            </option>
          ))}
        </select>
      </label>
      <LabelPicker
        labels={labels}
        template={template}
        value={category}
        readOnly={readOnly}
        onChange={onLabel}
      />
      <button type="button" disabled={readOnly || !category} onClick={onAdd}>
        {t("wbKeypointAdd")}
      </button>
      <button
        type="button"
        disabled={readOnly || selected < 0}
        onClick={onDelete}
      >
        {t("wbEditorDelete")}
      </button>
    </>
  );
}
