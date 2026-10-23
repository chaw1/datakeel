import { useI18n } from "../i18n/useI18n";

import "./evidence-signatures.css";

export type AnchorRange = {
  start: number;
  end: number;
  id: string;
  number: number;
};
export function Anchor({
  text,
  ranges,
  activeId = "",
  onActive,
}: {
  text: string;
  ranges: AnchorRange[];
  activeId?: string;
  onActive?: (id: string) => void;
}) {
  const { t } = useI18n();
  const characters = Array.from(text.normalize("NFC"));
  const parts: { start: number; text: string; ranges: AnchorRange[] }[] = [];
  characters.forEach((character, index) => {
    const matches = ranges.filter(
      (range) =>
        Number.isInteger(range.start) &&
        Number.isInteger(range.end) &&
        range.start >= 0 &&
        range.end <= characters.length &&
        range.start <= index &&
        index < range.end,
    );
    const previous = parts.at(-1);
    if (
      previous &&
      previous.ranges.length === matches.length &&
      previous.ranges.every((range, at) => range === matches[at])
    )
      previous.text += character;
    else parts.push({ start: index, text: character, ranges: matches });
  });
  return (
    <span className="anchor-text">
      {parts.map((part) => {
        const first = part.ranges.at(0);
        if (!first) return <span key={part.start}>{part.text}</span>;
        const numbers = [
          ...new Set(part.ranges.map((range) => range.number)),
        ].join(",");
        return (
          <button
            type="button"
            key={part.start}
            className={`evidence-anchor${part.ranges.some((range) => range.id === activeId) ? " is-linked" : ""}`}
            data-anchor-id={first.id}
            data-anchor-number={numbers}
            aria-label={t("evAnchorLabel", {
              number: numbers,
              text: part.text,
            })}
            onMouseEnter={() => onActive?.(first.id)}
            onMouseLeave={() => onActive?.("")}
            onFocus={() => onActive?.(first.id)}
            onBlur={() => onActive?.("")}
            onClick={() => onActive?.(first.id)}
          >
            <mark>{part.text}</mark>
            <sup>{numbers}</sup>
          </button>
        );
      })}
    </span>
  );
}
