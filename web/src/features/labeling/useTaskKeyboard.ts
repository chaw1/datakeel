import { useEffect } from "react";

import type { RefObject } from "react";

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
          !event.target.readOnly) ||
        (event.target instanceof HTMLInputElement &&
          !["checkbox", "radio", "button", "range"].includes(
            event.target.type,
          )) ||
        (event.target instanceof HTMLElement && event.target.isContentEditable);
      const modifier = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
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
      } else if (event.altKey && ["n", "p"].includes(key)) {
        event.preventDefault();
        actions.navigate(key === "n" ? 1 : -1);
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
