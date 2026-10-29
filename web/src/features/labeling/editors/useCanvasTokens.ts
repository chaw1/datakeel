import { useEffect, useState } from "react";

function readTokens() {
  const style = getComputedStyle(document.documentElement);
  return {
    ink: style.getPropertyValue("--ink").trim(),
    background: style.getPropertyValue("--sheet").trim(),
    accent: style.getPropertyValue("--pencil").trim(),
    error: style.getPropertyValue("--red").trim(),
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
