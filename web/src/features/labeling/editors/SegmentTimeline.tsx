import { useRef, useState } from "react";

import { useI18n } from "../../../i18n/useI18n";

import { SegmentBlocks } from "./SegmentBlocks";
import { SegmentMedia } from "./SegmentMedia";
import {
  draftSegment,
  editSegment,
  formatTime,
  visibleSegments,
} from "./segments";

import type { SegmentEditMode } from "./segments";
import type { AnnotationSegment, Attributes } from "./types";

interface DragState {
  mode: SegmentEditMode | "create";
  index: number;
  anchor: number;
  original?: AnnotationSegment;
}

export function SegmentTimeline({
  duration,
  segments,
  mediaUrl,
  mediaType,
  currentTime,
  zoom,
  selected,
  category,
  attributes,
  readOnly,
  onSeek,
  onChange,
  onSelect,
  onZoom,
  setMedia,
  onPlaying,
}: {
  duration: number;
  segments: readonly AnnotationSegment[];
  mediaUrl: string;
  mediaType: string;
  currentTime: number;
  zoom: number;
  selected: number;
  category: string;
  attributes: Attributes;
  readOnly?: boolean;
  onSeek: (milliseconds: number) => void;
  onChange: (segments: AnnotationSegment[]) => void;
  onSelect: (index: number) => void;
  onZoom: (zoom: number) => void;
  setMedia: (node: HTMLMediaElement | null) => void;
  onPlaying: (playing: boolean) => void;
}) {
  const { t } = useI18n();
  const [offsetState, setOffset] = useState(0);
  const [preview, setPreview] = useState<{
    index: number;
    segment: AnnotationSegment;
  } | null>(null);
  const drag = useRef<DragState | null>(null);
  const previewRef = useRef<{
    index: number;
    segment: AnnotationSegment;
  } | null>(null);
  const track = useRef<HTMLDivElement | null>(null);
  const windowSize = Math.max(1, duration / zoom);
  const offset = Math.min(offsetState, Math.max(0, duration - windowSize));
  const windowEnd = Math.min(duration, offset + windowSize);

  const displayed = preview
    ? preview.index < 0
      ? [...segments, preview.segment]
      : segments.map((item, index) =>
          index === preview.index ? preview.segment : item,
        )
    : [...segments];
  const positioned = visibleSegments(displayed, offset, windowEnd);
  const lanes = Math.max(1, ...positioned.map((item) => item.lane + 1));
  const playheadLeft = Math.max(
    0,
    Math.min(100, ((currentTime - offset) / windowSize) * 100),
  );

  function timeAt(event: React.PointerEvent<HTMLElement>) {
    const bounds = track.current?.getBoundingClientRect();
    if (!bounds) return 0;
    const ratio = Math.max(
      0,
      Math.min(1, (event.clientX - bounds.left) / bounds.width),
    );
    return offset + ratio * windowSize;
  }
  function startDrag(event: React.PointerEvent<HTMLElement>, state: DragState) {
    if (readOnly || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = state;
    if (state.index >= 0) onSelect(state.index);
  }
  function updatePreview(value: typeof preview) {
    previewRef.current = value;
    setPreview(value);
  }
  function moveDrag(event: React.PointerEvent<HTMLElement>) {
    const active = drag.current;
    if (!active) return;
    const time = timeAt(event);
    if (active.mode === "create") {
      const segment = draftSegment(
        active.anchor,
        time,
        category,
        attributes,
        duration,
      );
      updatePreview(segment ? { index: -1, segment } : null);
    } else if (active.original) {
      updatePreview({
        index: active.index,
        segment: editSegment(
          active.original,
          active.mode,
          Math.round(time - active.anchor),
          duration,
        ),
      });
    }
  }
  function finishDrag(commit: boolean) {
    const completed = previewRef.current;
    drag.current = null;
    if (commit && completed) {
      const next =
        completed.index < 0
          ? [...segments, completed.segment]
          : segments.map((item, index) =>
              index === completed.index ? completed.segment : item,
            );
      onChange(next);
      onSelect(completed.index < 0 ? segments.length : completed.index);
    }
    updatePreview(null);
  }
  return (
    <div className="wb-segment-player">
      <SegmentMedia
        mediaUrl={mediaUrl}
        mediaType={mediaType}
        setMedia={setMedia}
        onPlaying={onPlaying}
      />
      <div className="wb-editor-toolbar">
        <button
          type="button"
          disabled={zoom >= 64}
          onClick={() => {
            onZoom(Math.min(64, zoom * 2));
          }}
        >
          {t("wbEditorZoomIn")}
        </button>
        <button
          type="button"
          disabled={zoom <= 1}
          onClick={() => {
            onZoom(Math.max(1, zoom / 2));
          }}
        >
          {t("wbEditorZoomOut")}
        </button>
        <button
          type="button"
          onClick={() => {
            onZoom(1);
          }}
        >
          {t("wbSegmentFit")}
        </button>
        <span>{formatTime(currentTime)}</span>
      </div>
      <label>
        {t("wbSegmentPlayhead")}
        <input
          type="range"
          min={0}
          max={duration}
          step={1}
          value={Math.round(currentTime)}
          onChange={(event) => {
            onSeek(event.target.valueAsNumber);
          }}
        />
      </label>
      <label>
        {t("wbSegmentPan")}
        <input
          type="range"
          min={0}
          max={Math.max(0, duration - windowSize)}
          step={1}
          value={offset}
          disabled={zoom <= 1}
          onChange={(event) => {
            setOffset(event.target.valueAsNumber);
          }}
        />
      </label>
      <div className="wb-segment-ruler" aria-hidden="true">
        {Array.from({ length: 6 }, (_, index) => (
          <span key={index}>
            {formatTime(offset + (windowSize * index) / 5)}
          </span>
        ))}
      </div>
      <div
        ref={track}
        className="wb-segment-lanes"
        role="group"
        aria-label={t("wbSegmentTimeline")}
        style={{ height: Math.max(72, Math.min(240, lanes * 34)) }}
        onPointerDown={(event) => {
          startDrag(event, {
            mode: "create",
            index: -1,
            anchor: timeAt(event),
          });
        }}
        onPointerMove={moveDrag}
        onPointerUp={() => {
          finishDrag(true);
        }}
        onPointerCancel={() => {
          finishDrag(false);
        }}
      >
        <div className="wb-segment-track" style={{ height: lanes * 34 }}>
          <SegmentBlocks
            positioned={positioned}
            segments={segments}
            selected={selected}
            offset={offset}
            windowSize={windowSize}
            readOnly={readOnly}
            onSelect={onSelect}
            onDrag={(event, mode, index, original) => {
              startDrag(event, {
                mode,
                index,
                anchor: timeAt(event),
                original,
              });
            }}
          />
          <div
            className="wb-segment-playhead"
            style={{
              left: `${String(playheadLeft)}%`,
            }}
          />
        </div>
      </div>
    </div>
  );
}
