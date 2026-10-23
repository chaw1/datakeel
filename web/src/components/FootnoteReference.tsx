import { footnoteMarker } from "./Footnotes";

import type { FootnoteItem } from "./Footnotes";

export function FootnoteReference({
  item,
  index,
}: {
  item: FootnoteItem;
  index: number;
}) {
  return (
    <sup className="footnote-reference">
      <a
        href={`#footnote-${encodeURIComponent(item.id)}`}
        aria-label={`${footnoteMarker(index)} · ${item.label}`}
        onClick={(event) => {
          event.preventDefault();
          const target = document.getElementById(
            `footnote-${encodeURIComponent(item.id)}`,
          );
          const detail = target?.querySelector("details");
          if (detail) detail.open = true;
          target?.querySelector<HTMLElement>("summary, a, button")?.focus();
          if (target && typeof target.scrollIntoView === "function")
            target.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }}
      >
        {footnoteMarker(index)}
      </a>
    </sup>
  );
}
