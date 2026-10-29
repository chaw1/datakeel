import { useI18n } from "../../../i18n/useI18n";

import type { AnnotationSpan, ProductionLabel } from "./types";

export function SpanPreview({
  text,
  spans,
  labels,
}: {
  text: string;
  spans: readonly AnnotationSpan[];
  labels: readonly ProductionLabel[];
}) {
  const { t } = useI18n();
  const characters = Array.from(text);
  const boundaries = [
    ...new Set([
      0,
      characters.length,
      ...spans.flatMap((span) => [span.start, span.end]),
    ]),
  ]
    .filter((offset) => offset >= 0 && offset <= characters.length)
    .sort((a, b) => a - b);
  return (
    <div className="wb-span-preview" aria-label={t("wbEditorSpanPreview")}>
      {boundaries.slice(0, -1).map((start, index) => {
        const end = boundaries[index + 1];
        const active = spans.filter(
          (span) => span.start <= start && span.end >= end,
        );
        const content = characters.slice(start, end).join("");
        return active.length ? (
          <mark
            key={start}
            className="wb-span-mark"
            data-nested={active.length > 1}
            title={active
              .map(
                (span) =>
                  labels.find((label) => label.id === span.category)?.name ??
                  span.category,
              )
              .join(" · ")}
          >
            {content}
          </mark>
        ) : (
          <span key={start}>{content}</span>
        );
      })}
    </div>
  );
}
