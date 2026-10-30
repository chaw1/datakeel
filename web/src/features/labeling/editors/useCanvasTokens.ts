import { useEffect, useState } from "react";

import { LABEL_PALETTE_SIZE } from "./labelColors";

export type CanvasTokens = ReturnType<typeof readTokens>;

function readTokens() {
  const style = getComputedStyle(document.documentElement);
  return {
    ink: style.getPropertyValue("--ink").trim(),
    background: style.getPropertyValue("--sheet").trim(),
    accent: style.getPropertyValue("--pencil").trim(),
    error: style.getPropertyValue("--red").trim(),
    labels: Array.from({ length: LABEL_PALETTE_SIZE }, (_, index) =>
      style.getPropertyValue(`--label-${String(index + 1)}`).trim(),
    ),
  };
}
export function useCanvasTokens() {
  const [tokens, setTokens] = useState(readTokens);
  useEffect(() => {
    const refresh = () => {
      setTokens(readTokens());
    };
    const observer = new MutationObserver(refresh);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "data-palette", "class"],
    });
    const scheme =
      typeof window.matchMedia === "function"
        ? window.matchMedia("(prefers-color-scheme: dark)")
        : null;
    scheme?.addEventListener("change", refresh);
    return () => {
      observer.disconnect();
      scheme?.removeEventListener("change", refresh);
    };
  }, []);
  return tokens;
}
