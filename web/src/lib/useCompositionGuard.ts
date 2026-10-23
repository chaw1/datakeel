import { useCallback, useEffect, useRef } from "react";

export function useCompositionGuard() {
  const composing = useRef(false);
  useEffect(() => {
    const start = () => {
      composing.current = true;
    };
    const end = () => {
      composing.current = false;
    };
    document.addEventListener("compositionstart", start, true);
    document.addEventListener("compositionend", end, true);
    window.addEventListener("blur", end);
    return () => {
      document.removeEventListener("compositionstart", start, true);
      document.removeEventListener("compositionend", end, true);
      window.removeEventListener("blur", end);
    };
  }, []);
  return useCallback(
    (event?: { isComposing?: boolean; keyCode?: number }) =>
      composing.current ||
      event?.isComposing === true ||
      event?.keyCode === 229,
    [],
  );
}
