import { useI18n } from "../../../i18n/useI18n";

import type { PositionedSegment, SegmentEditMode } from "./segments";
import type { AnnotationSegment } from "./types";

export function SegmentBlocks({
  positioned,
  segments,
  selected,
  offset,
  windowSize,
  readOnly,
  onSelect,
  onDrag,
}: {
  positioned: readonly PositionedSegment[];
  segments: readonly AnnotationSegment[];
  selected: number;
  offset: number;
  windowSize: number;
  readOnly?: boolean;
  onSelect: (index: number) => void;
  onDrag: (
    event: React.PointerEvent<HTMLElement>,
    mode: SegmentEditMode,
    index: number,
    original: AnnotationSegment,
  ) => void;
}) {
  const { t } = useI18n();
  return (
    <>
      {positioned.map(({ segment, index, lane }) => {
        const left = ((segment.start_ms - offset) / windowSize) * 100;
        const width = ((segment.end_ms - segment.start_ms) / windowSize) * 100;
        return (
          <div
            className="wb-segment-block"
            key={index}
            data-selected={index === selected}
            style={{
              left: `${String(Math.max(0, left))}%`,
              width: `${String(Math.max(0.2, width))}%`,
              top: lane * 34,
            }}
          >
            <button
              type="button"
              className="wb-segment-resize"
              aria-label={t("wbSegmentResizeStart", { index: index + 1 })}
              disabled={readOnly}
              onPointerDown={(event) => {
                onDrag(event, "start", index, segments[index]);
              }}
            />
            <button
              type="button"
              className="wb-segment-body"
              aria-pressed={index === selected}
              onClick={() => {
                onSelect(index);
              }}
              onPointerDown={(event) => {
                onDrag(event, "move", index, segments[index]);
              }}
            >
              {segment.category}
            </button>
            <button
              type="button"
              className="wb-segment-resize"
              aria-label={t("wbSegmentResizeEnd", { index: index + 1 })}
              disabled={readOnly}
              onPointerDown={(event) => {
                onDrag(event, "end", index, segments[index]);
              }}
            />
          </div>
        );
      })}
    </>
  );
}
