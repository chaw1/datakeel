import { useEffect, useRef, useState } from "react";

export function useGraphScroll(width: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState({ left: false, right: false });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => {
      setOverflow({
        left: element.scrollLeft > 1,
        right:
          element.scrollWidth - element.clientWidth - element.scrollLeft > 1,
      });
    };
    measure();
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(measure);
    observer?.observe(element);
    element.addEventListener("scroll", measure);
    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      element.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, [width]);
  function scroll(direction: number) {
    const element = ref.current;
    if (element)
      element.scrollTo({
        left: direction > 0 ? element.scrollWidth : 0,
        behavior: "smooth",
      });
  }
  return { ref, overflow, scroll };
}
