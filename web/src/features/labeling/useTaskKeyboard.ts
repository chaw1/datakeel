import { useEffect } from "react";

import { isSelectableSource } from "./editors/geometry";

import type { RefObject } from "react";

/**
 * Read Alt/Option+N/P by physical key: macOS Option turns N into a dead key and P into
 * "π", so `event.key` alone never matches there. Layouts without a KeyN/KeyP code fall back to the key.
 */
export function navigationDirection(event: KeyboardEvent): -1 | 1 | null {
  if (event.code === "KeyN") return 1;
  if (event.code === "KeyP") return -1;
  const key = event.key.toLowerCase();
  return key === "n" ? 1 : key === "p" ? -1 : null;
}

export function useTaskKeyboard(
  root: RefObject<HTMLDivElement | null>,
  actions: {
    editable: boolean;
    save: () => void;
    submit: () => void;
    undo: () => void;
    redo: () => void;
    navigate: (direction: -1 | 1) => void;
    help: () => void;
  },
) {
  useEffect(() => {
    const element = root.current;
    if (!element) return;
    function handle(event: KeyboardEvent) {
      if (event.isComposing || event.defaultPrevented) return;
      const typing =
        (event.target instanceof HTMLTextAreaElement &&
          !isSelectableSource(event.target)) ||
        (event.target instanceof HTMLInputElement &&
          !["checkbox", "radio", "button", "range"].includes(
            event.target.type,
          )) ||
        (event.target instanceof HTMLElement && event.target.isContentEditable);
      const modifier = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      const direction =
        event.altKey && !modifier ? navigationDirection(event) : null;
      if (modifier && key === "s") {
        event.preventDefault();
        actions.save();
      } else if (modifier && key === "enter") {
        event.preventDefault();
        actions.submit();
      } else if (modifier && key === "z" && actions.editable && !typing) {
        event.preventDefault();
        if (event.shiftKey) actions.redo();
        else actions.undo();
      } else if (modifier && key === "y" && actions.editable && !typing) {
        event.preventDefault();
        actions.redo();
      } else if (direction) {
        event.preventDefault();
        actions.navigate(direction);
      } else if (event.key === "?" && !typing) {
        event.preventDefault();
        actions.help();
      }
    }
    element.addEventListener("keydown", handle);
    return () => {
      element.removeEventListener("keydown", handle);
    };
  }, [root, actions]);
}
