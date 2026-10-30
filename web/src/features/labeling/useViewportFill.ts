import { useLayoutEffect, useState } from "react";

import type { RefObject } from "react";

const BOTTOM_GAP = 8;

/**
 * Size an element to the visible viewport below its own top edge, so the canvas
 * takes all remaining height without a page scrollbar, and follow window resizes.
 */
export function useViewportFill(
  element: RefObject<HTMLElement | null>,
  active: boolean,
): number | undefined {
  const [height, setHeight] = useState<number>();
  useLayoutEffect(() => {
    if (!active) return;
    function measure() {
      const node = element.current;
      if (!node) return;
      const top = node.getBoundingClientRect().top + window.scrollY;
      setHeight(
        Math.max(320, Math.floor(window.innerHeight - top - BOTTOM_GAP)),
      );
    }
    if (window.scrollY > 0) window.scrollTo({ top: 0 });
    measure();
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("resize", measure);
    };
  }, [element, active]);
  return active ? height : undefined;
}
