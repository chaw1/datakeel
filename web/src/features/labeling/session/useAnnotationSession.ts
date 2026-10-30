import { useEffect, useState, useSyncExternalStore } from "react";

import { AnnotationSession } from "./AnnotationSession";

import type { SessionOptions } from "./types";

/** Mount this hook in a component keyed by actor, project and production task. */
export function useAnnotationSession(options: SessionOptions) {
  const [session] = useState(() => new AnnotationSession(options));
  const snapshot = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const { save, reload, validate } = options;
  useEffect(() => {
    session.setAdapters(save, reload, validate);
  }, [session, save, reload, validate]);
  useEffect(() => {
    const online = () => {
      session.setOnline(true);
    };
    const offline = () => {
      session.setOnline(false);
    };
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!session.getSnapshot().dirty) return;
      event.preventDefault();
    };
    window.addEventListener("online", online);
    window.addEventListener("offline", offline);
    window.addEventListener("beforeunload", beforeUnload);
    session.start();
    return () => {
      window.removeEventListener("online", online);
      window.removeEventListener("offline", offline);
      window.removeEventListener("beforeunload", beforeUnload);
      session.dispose();
    };
  }, [session]);
  return {
    ...snapshot,
    edit: session.edit,
    undo: session.undo,
    redo: session.redo,
    flush: session.flush,
    reload: session.reload,
    overwrite: session.overwrite,
  };
}
