import { useState } from "react";

import { useI18n } from "../../../i18n/useI18n";

import { attributeFields, withDefaults } from "./attributes";
import { isTyping, keyStep } from "./geometry";
import { KeyboardRegion } from "./KeyboardRegion";
import { SegmentDetails } from "./SegmentDetails";
import { defaultSegment, editSegment } from "./segments";
import { SegmentTimeline } from "./SegmentTimeline";
import { shortcutLabel } from "./shortcuts";
import { useMediaPlayback } from "./useMediaPlayback";

import type { SegmentEditMode } from "./segments";
import type { AnnotationSegment, EditorProps } from "./types";

export function SegmentEditor(props: EditorProps) {
  const { value, labels, onChange, readOnly } = props;
  const { t } = useI18n();
  const duration = props.durationMs ?? value.media_duration_ms ?? 0;
  const mediaUrl = props.mediaUrl ?? "";
  const playback = useMediaPlayback(duration);
  const segments = value.segments ?? [];
  const [selected, setSelected] = useState(-1);
  const [category, setCategory] = useState(labels[0]?.id ?? "");
  const [mode, setMode] = useState<SegmentEditMode>("move");
  const [zoom, setZoom] = useState(1);
  const selectedIndex = Math.min(selected, segments.length - 1);
  const current = segments.at(selectedIndex);

  function change(next: AnnotationSegment[]) {
    if (!readOnly)
      onChange({ ...value, segments: next, media_duration_ms: duration });
  }
  function update(segment: AnnotationSegment) {
    change(
      segments.map((item, index) => (index === selectedIndex ? segment : item)),
    );
  }
  function add(playhead = playback.currentTime) {
    const label = current?.category ?? category;
    if (readOnly || !label || duration <= 0) return;
    const attributes = withDefaults(
      {},
      attributeFields(props.template, "object"),
    );
    change([
      ...segments,
      defaultSegment(playhead, label, attributes, duration),
    ]);
    setSelected(segments.length);
  }
  function remove() {
    if (readOnly || !current) return;
    change(segments.filter((_, index) => index !== selectedIndex));
    setSelected(Math.min(selectedIndex, segments.length - 2));
  }
  function adjust(delta: number) {
    if (current && !readOnly)
      update(editSegment(current, mode, delta, duration));
  }
  function select(index: number) {
    setSelected(index);
    const label = segments.at(index)?.category;
    if (label) setCategory(label);
  }
  if (!duration)
    return (
      <section
        className="wb-annotation-editor"
        aria-label={t("wbEditorSegment")}
      >
        <p role="alert">{t("wbSegmentProbeMissing")}</p>
      </section>
    );

  return (
    <KeyboardRegion
      label={t("wbEditorSegment")}
      onKeyDown={(event) => {
        if (
          isTyping(event.target) ||
          event.target instanceof HTMLMediaElement ||
          event.isComposing ||
          event.ctrlKey ||
          event.metaKey ||
          event.altKey
        )
          return;
        const key = event.key.toLowerCase();
        const step = keyStep(event);
        if (key === " " && !(event.target instanceof HTMLButtonElement)) {
          event.preventDefault();
          playback.toggle();
        } else if (key === "," || key === ".") {
          event.preventDefault();
          playback.seek(
            playback.currentTime + (key === "," ? -1 : 1) * 10 * step,
          );
        } else if (["+", "=", "-", "0"].includes(key)) {
          event.preventDefault();
          setZoom(
            key === "0"
              ? 1
              : Math.max(1, Math.min(64, zoom * (key === "-" ? 0.5 : 2))),
          );
        } else if (["[", "]"].includes(key) && segments.length) {
          event.preventDefault();
          select(
            (Math.max(0, selectedIndex) +
              (key === "]" ? 1 : -1) +
              segments.length) %
              segments.length,
          );
        } else if (["i", "o"].includes(key) && current) {
          event.preventDefault();
          playback.seek(key === "i" ? current.start_ms : current.end_ms);
        } else if (key === "t") {
          event.preventDefault();
          add();
        } else if (key === "r" && !readOnly) {
          event.preventDefault();
          setMode(
            ({ move: "start", start: "end", end: "move" } as const)[mode],
          );
        } else if (["delete", "backspace"].includes(key)) {
          event.preventDefault();
          remove();
        } else if (
          ["arrowleft", "arrowdown", "arrowright", "arrowup"].includes(key)
        ) {
          event.preventDefault();
          adjust((["arrowleft", "arrowdown"].includes(key) ? -1 : 1) * step);
        } else {
          const picked = shortcutLabel(event, labels, props.template);
          if (picked) {
            event.preventDefault();
            setCategory(picked.id);
            if (current && !readOnly)
              update({ ...current, category: picked.id });
          }
        }
      }}
    >
      {labels.length === 0 && <p role="status">{t("wbEditorNoLabels")}</p>}
      <div className="wb-editor-toolbar">
        <button
          type="button"
          disabled={readOnly || !labels.length}
          onClick={() => {
            add();
          }}
        >
          {t("wbSegmentAdd")}
        </button>
        <button type="button" disabled={readOnly || !current} onClick={remove}>
          {t("wbEditorDelete")}
        </button>
        <span>
          {t("wbSegmentEditMode", { mode: t(`wbSegmentMode_${mode}`) })}
        </span>
      </div>
      <p className="muted">{t("wbSegmentHint")}</p>
      <SegmentTimeline
        duration={duration}
        segments={segments}
        mediaUrl={mediaUrl}
        mediaType={props.mediaType ?? "audio/wav"}
        currentTime={playback.currentTime}
        zoom={zoom}
        selected={selectedIndex}
        category={current?.category ?? category}
        attributes={withDefaults({}, attributeFields(props.template, "object"))}
        readOnly={readOnly}
        onSeek={playback.seek}
        onChange={change}
        onSelect={select}
        onZoom={setZoom}
        setMedia={playback.setMedia}
        onPlaying={playback.setPlaying}
      />
      <SegmentDetails
        {...props}
        duration={duration}
        selected={selectedIndex}
        onSelect={select}
        onUpdate={update}
      />
    </KeyboardRegion>
  );
}
