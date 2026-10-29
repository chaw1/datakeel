import { useEffect, useRef, useState } from "react";

import { useI18n } from "../../../i18n/useI18n";

import { CoordinateField } from "./CoordinateField";
import { textareaCharacterOffset, isTyping } from "./geometry";
import { KeyboardRegion } from "./KeyboardRegion";
import { LabelPicker } from "./LabelPicker";
import { ShapeProperties } from "./ShapeProperties";
import { shortcutLabel } from "./shortcuts";
import { SpanPreview } from "./SpanPreview";

import type { AnnotationSpan, EditorProps } from "./types";

export function SpanEditor({
  value,
  labels,
  template,
  text = "",
  onChange,
  readOnly,
}: EditorProps) {
  const { t } = useI18n();
  const source = useRef<HTMLTextAreaElement>(null);
  const sourceSelection = useRef({ start: 0, end: 0 });
  const [label, setLabel] = useState(labels[0]?.id ?? "");
  const [range, setRange] = useState({ start: 0, end: 0 });
  const [selected, setSelected] = useState(-1);
  const spans = value.spans ?? [];
  const current = selected >= 0 ? spans.at(selected) : undefined;
  const textLength = Array.from(text).length;
  const characters = Array.from(text);
  const category = labels.some((item) => item.id === label)
    ? label
    : (labels[0]?.id ?? "");
  useEffect(() => {
    // A read-only textarea ignores Shift + arrows in Chromium, so the source stays
    // editable for selection and refuses every text change instead.
    const node = source.current;
    const refuse = (event: Event) => {
      event.preventDefault();
    };
    node?.addEventListener("beforeinput", refuse);
    return () => {
      node?.removeEventListener("beforeinput", refuse);
    };
  }, []);
  function update(span: AnnotationSpan) {
    if (!readOnly)
      onChange({
        ...value,
        text_length: textLength,
        spans: spans.map((item, index) => (index === selected ? span : item)),
      });
  }
  function add(start = range.start, end = range.end) {
    if (readOnly || !category || start < 0 || end <= start || end > textLength)
      return;
    onChange({
      ...value,
      text_length: textLength,
      spans: [...spans, { category, start, end, attributes: {} }],
    });
    // Stay on a new selection: the offsets must never silently edit the span just added.
    setRange({ start, end });
    setSelected(-1);
  }
  function remove() {
    if (readOnly || !current) return;
    onChange({
      ...value,
      spans: spans.filter((_, index) => index !== selected),
    });
    setSelected(-1);
  }
  function selection(node: HTMLTextAreaElement) {
    return {
      start: textareaCharacterOffset(text, node.selectionStart),
      end: textareaCharacterOffset(text, node.selectionEnd),
    };
  }
  const coordinates = current ?? range;
  return (
    <KeyboardRegion
      label={t("wbEditorSpan")}
      onKeyDown={(event) => {
        if (readOnly || isTyping(event.target)) return;
        if (event.key === "Escape" && current) {
          event.preventDefault();
          setSelected(-1);
        } else if (event.key === "Delete" || event.key === "Backspace") {
          event.preventDefault();
          remove();
        } else {
          const picked = shortcutLabel(event, labels, template);
          if (picked) {
            event.preventDefault();
            setLabel(picked.id);
            if (current) update({ ...current, category: picked.id });
          }
        }
      }}
    >
      <p className="muted">{t("wbEditorSpanHint")}</p>
      {labels.length === 0 && <p role="status">{t("wbEditorNoLabels")}</p>}
      <LabelPicker
        labels={labels}
        template={template}
        value={current?.category ?? category}
        readOnly={readOnly}
        onChange={(next) => {
          setLabel(next);
          if (current) update({ ...current, category: next });
        }}
      />
      <label>
        {t("wbEditorSourceText")}
        <textarea
          ref={source}
          className="wb-span-source"
          value={text}
          aria-readonly="true"
          inputMode="none"
          spellCheck={false}
          onChange={() => undefined}
          onSelect={(event) => {
            const next = selection(event.currentTarget);
            // Focus alone (e.g. tabbing through) must not replace typed offsets.
            const last = sourceSelection.current;
            if (next.start === last.start && next.end === last.end) return;
            sourceSelection.current = next;
            setRange(next);
            if (next.end > next.start) setSelected(-1);
          }}
          onKeyDown={(event) => {
            if (
              event.defaultPrevented ||
              event.ctrlKey ||
              event.metaKey ||
              event.altKey
            )
              return;
            if (event.key === "Enter") {
              event.preventDefault();
              const next = selection(event.currentTarget);
              add(next.start, next.end);
            }
          }}
        />
      </label>
      <p className="muted" aria-live="polite">
        {current
          ? t("wbEditorSpanEditing", {
              start: current.start,
              end: current.end,
            })
          : t("wbEditorSpanNew")}
      </p>
      <div className="wb-coordinate-fields">
        <CoordinateField
          label={t("wbEditorStart")}
          value={coordinates.start}
          max={textLength}
          readOnly={readOnly}
          onChange={(start) => {
            setRange({ ...range, start });
            if (current && start < current.end) update({ ...current, start });
          }}
        />
        <CoordinateField
          label={t("wbEditorEnd")}
          value={coordinates.end}
          max={textLength}
          readOnly={readOnly}
          onChange={(end) => {
            setRange({ ...range, end });
            if (current && end > current.start) update({ ...current, end });
          }}
        />
        <button
          type="button"
          disabled={
            readOnly || !category || coordinates.end <= coordinates.start
          }
          onClick={() => {
            add(coordinates.start, coordinates.end);
          }}
        >
          {t("wbEditorAddSpan")}
        </button>
        <button type="button" disabled={readOnly || !current} onClick={remove}>
          {t("wbEditorDelete")}
        </button>
        <button
          type="button"
          disabled={!current}
          onClick={() => {
            setSelected(-1);
          }}
        >
          {t("wbEditorNewSpan")}
        </button>
      </div>
      <SpanPreview text={text} spans={spans} labels={labels} />
      <ul className="wb-span-list" aria-label={t("wbEditorSpans")}>
        {spans.map((span, index) => (
          <li key={index}>
            <button
              type="button"
              aria-pressed={selected === index}
              onClick={() => {
                setSelected(index);
                setRange({ start: span.start, end: span.end });
              }}
            >
              {labels.find((item) => item.id === span.category)?.name ??
                span.category}
              {" · "}
              {span.start}
              {"–"}
              {span.end}
              {" · "}
              {characters.slice(span.start, span.end).join("")}
            </button>
          </li>
        ))}
      </ul>
      {current && (
        <ShapeProperties
          value={current.attributes}
          readOnly={readOnly}
          onChange={(attributes) => {
            update({ ...current, attributes });
          }}
        />
      )}
    </KeyboardRegion>
  );
}
