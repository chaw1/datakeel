import { useI18n } from "../../i18n/useI18n";

import type { EvidenceSample } from "../../api/types";

export function SamplePreview({
  sample,
  boxes = sample.annotation_boxes,
  activeId = "",
  numbers = [],
}: {
  sample: EvidenceSample;
  boxes?: EvidenceSample["annotation_boxes"];
  activeId?: string;
  numbers?: string[];
}) {
  const { t } = useI18n();
  if (!sample.thumbnail_url)
    return (
      <div
        className="evidence-image image-unavailable"
        role="img"
        aria-label={t("evNoImage")}
      >
        <span>{t("evNoImage")}</span>
      </div>
    );
  return (
    <div className="evidence-image">
      <img src={sample.thumbnail_url} alt={sample.filename} loading="lazy" />
      {boxes.map((box, index) => (
        <span
          className={`annotation-box${activeId === box.concept ? " is-linked" : ""}`}
          data-anchor-id={box.concept}
          data-anchor-number={
            numbers.includes(box.concept)
              ? numbers.indexOf(box.concept) + 1
              : undefined
          }
          key={`${box.concept}-${String(index)}`}
          role="img"
          aria-label={t("evOverlay", { concept: box.concept })}
          style={{
            left: `${String((box.bbox[0] / box.width) * 100)}%`,
            top: `${String((box.bbox[1] / box.height) * 100)}%`,
            width: `${String(((box.bbox[2] - box.bbox[0]) / box.width) * 100)}%`,
            height: `${String(((box.bbox[3] - box.bbox[1]) / box.height) * 100)}%`,
          }}
        >
          <span>
            {numbers.includes(box.concept)
              ? `${String(numbers.indexOf(box.concept) + 1)} · `
              : ""}
            {box.concept}
          </span>
        </span>
      ))}
    </div>
  );
}
