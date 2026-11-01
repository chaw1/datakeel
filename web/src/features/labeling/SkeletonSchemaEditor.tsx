import { useI18n } from "../../i18n/useI18n";

import { nextPointId } from "./skeletonSchema";

import type { SkeletonDefinition } from "./editors/types";

export function SkeletonSchemaEditor({
  value,
  onChange,
}: {
  value: SkeletonDefinition;
  onChange: (value: SkeletonDefinition) => void;
}) {
  const { t } = useI18n();
  const ids = value.points.map((point) => point.id);
  function changeEdge(index: number, side: 0 | 1, id: string) {
    onChange({
      ...value,
      edges: value.edges.map((edge, i): [string, string] =>
        i === index ? (side === 0 ? [id, edge[1]] : [edge[0], id]) : edge,
      ),
    });
  }
  return (
    <fieldset className="wb-skeleton-schema">
      <legend>{t("wbSkeletonSchema")}</legend>
      <h4>{t("wbSkeletonPoints")}</h4>
      {value.points.map((point, index) => (
        <div className="wb-skeleton-point" key={`${point.id}:${String(index)}`}>
          <label>
            {t("wbKeypointId")}
            <input
              value={point.id}
              onChange={(event) => {
                onChange({
                  ...value,
                  points: value.points.map((item, i) =>
                    i === index ? { ...item, id: event.target.value } : item,
                  ),
                });
              }}
            />
          </label>
          <label>
            {t("wbKeypointName")}
            <input
              value={point.name}
              onChange={(event) => {
                onChange({
                  ...value,
                  points: value.points.map((item, i) =>
                    i === index ? { ...item, name: event.target.value } : item,
                  ),
                });
              }}
            />
          </label>
          {(["name_zh", "name_en"] as const).map((field) => (
            <label key={field}>
              {t(field === "name_zh" ? "wbKeypointNameZh" : "wbKeypointNameEn")}
              <input
                value={point[field] ?? ""}
                onChange={(event) => {
                  onChange({
                    ...value,
                    points: value.points.map((item, i) =>
                      i === index
                        ? { ...item, [field]: event.target.value || null }
                        : item,
                    ),
                  });
                }}
              />
            </label>
          ))}
          <label>
            <input
              type="checkbox"
              checked={point.required}
              onChange={(event) => {
                onChange({
                  ...value,
                  points: value.points.map((item, i) =>
                    i === index
                      ? { ...item, required: event.target.checked }
                      : item,
                  ),
                });
              }}
            />
            {t("wbAttributeRequired")}
          </label>
          <button
            type="button"
            disabled={index === 0}
            onClick={() => {
              const points = [...value.points];
              [points[index - 1], points[index]] = [
                points[index],
                points[index - 1],
              ];
              onChange({ ...value, points });
            }}
          >
            {t("wbMoveUp")}
          </button>
          <button
            type="button"
            disabled={index === value.points.length - 1}
            onClick={() => {
              const points = [...value.points];
              [points[index], points[index + 1]] = [
                points[index + 1],
                points[index],
              ];
              onChange({ ...value, points });
            }}
          >
            {t("wbMoveDown")}
          </button>
          <button
            type="button"
            disabled={value.points.length === 1}
            onClick={() => {
              onChange({
                points: value.points.filter((_, i) => i !== index),
                edges: value.edges.filter(
                  ([left, right]) => left !== point.id && right !== point.id,
                ),
              });
            }}
          >
            {t("wbEditorDelete")}
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => {
          const id = nextPointId(value);
          onChange({
            ...value,
            points: [
              ...value.points,
              {
                id,
                name: id,
                name_zh: id,
                name_en: id,
                required: false,
              },
            ],
          });
        }}
      >
        {t("wbAddKeypoint")}
      </button>
      <h4>{t("wbSkeletonEdges")}</h4>
      {value.edges.map(([left, right], index) => (
        <div className="wb-skeleton-edge" key={index}>
          {([0, 1] as const).map((side) => (
            <label key={side}>
              {t(side === 0 ? "wbEdgeFrom" : "wbEdgeTo")}
              <select
                value={side === 0 ? left : right}
                onChange={(event) => {
                  changeEdge(index, side, event.target.value);
                }}
                onBlur={(event) => {
                  changeEdge(index, side, event.target.value);
                }}
              >
                {ids.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <button
            type="button"
            onClick={() => {
              onChange({
                ...value,
                edges: value.edges.filter((_, i) => i !== index),
              });
            }}
          >
            {t("wbEditorDelete")}
          </button>
        </div>
      ))}
      <button
        type="button"
        disabled={!ids.length}
        onClick={() => {
          onChange({
            ...value,
            edges: [...value.edges, [ids[0], ids.at(-1) ?? ids[0]]],
          });
        }}
      >
        {t("wbAddSkeletonEdge")}
      </button>
    </fieldset>
  );
}
