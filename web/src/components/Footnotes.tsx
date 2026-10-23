import type { ReactNode } from "react";

import "./footnotes.css";

export type FootnoteItem = {
  id: string;
  label: string;
  href?: string;
  onExpand?: () => void;
  content?: ReactNode;
  className?: string;
};

export function uniqueFootnotes(items: FootnoteItem[]): FootnoteItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

export function footnoteMarker(index: number): string {
  let value = index + 1;
  let marker = "";
  while (value > 0) {
    value -= 1;
    marker = String.fromCharCode(97 + (value % 26)) + marker;
    value = Math.floor(value / 26);
  }
  return marker;
}

export function Footnotes({ items }: { items: FootnoteItem[] }) {
  return (
    <ol className="source-footnotes">
      {uniqueFootnotes(items).map((item, index) => (
        <li
          id={`footnote-${encodeURIComponent(item.id)}`}
          key={item.id}
          data-source-id={item.id}
        >
          <span className="footnote-marker" aria-hidden="true">
            {footnoteMarker(index)}
          </span>
          {item.content !== undefined ? (
            <details className={item.className}>
              <summary onClick={item.onExpand}>{item.label}</summary>
              <div className="footnote-content">{item.content}</div>
            </details>
          ) : item.href ? (
            <a href={item.href}>{item.label}</a>
          ) : (
            <button type="button" onClick={item.onExpand}>
              {item.label}
            </button>
          )}
        </li>
      ))}
    </ol>
  );
}
