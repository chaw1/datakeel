import { useEffect, useRef } from "react";

import type { ReactNode } from "react";

export function KeyboardRegion({
  label,
  children,
  onKeyDown,
}: {
  label: string;
  children: ReactNode;
  onKeyDown: (event: KeyboardEvent) => void;
}) {
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    const node = root.current;
    const handle = (event: KeyboardEvent) => {
      if (!event.isComposing && !event.defaultPrevented) onKeyDown(event);
    };
    node?.addEventListener("keydown", handle);
    return () => {
      node?.removeEventListener("keydown", handle);
    };
  }, [onKeyDown]);
  return (
    <section ref={root} className="wb-annotation-editor" aria-label={label}>
      {children}
    </section>
  );
}
