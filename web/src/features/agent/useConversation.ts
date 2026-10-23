import { useEffect, useRef, useState } from "react";

import { streamMessage } from "../../api/agent";
import { get } from "../../api/client";

import type { AgentEvent, Conversation } from "../../api/types";

type LiveTurn = {
  id: string;
  content: string;
  events: AgentEvent[];
  running: boolean;
  error: string;
};
const blank: LiveTurn = {
  id: "",
  content: "",
  events: [],
  running: false,
  error: "",
};
export function useConversation(id: string) {
  const [revision, setRevision] = useState(0);
  const key = `${id}:${String(revision)}`;
  const [loaded, setLoaded] = useState<{
    id: string;
    key: string;
    value: Conversation | null;
    error: string;
  }>({ id: "", key: "", value: null, error: "" });
  const [live, setLive] = useState<LiveTurn>(blank);
  const controller = useRef<AbortController | null>(null);
  const path = `/api/agent/conversations/${encodeURIComponent(id)}`;
  useEffect(() => {
    if (!id) return;
    let active = true;
    void get<Conversation>(path)
      .then((value) => {
        if (active) setLoaded({ id, key, value, error: "" });
      })
      .catch((error: unknown) => {
        if (active) setLoaded({ id, key, value: null, error: String(error) });
      });
    return () => {
      active = false;
    };
  }, [id, key, path]);
  useEffect(
    () => () => {
      controller.current?.abort();
    },
    [id],
  );
  async function send(content: string) {
    if (
      !id ||
      (controller.current && !controller.current.signal.aborted && live.running)
    )
      return;
    const request = new AbortController();
    controller.current = request;
    const interrupted = () => request.signal.aborted;
    setLive({ id, content, events: [], running: true, error: "" });
    let failure = "";
    try {
      await streamMessage(
        id,
        { content, idempotency_key: crypto.randomUUID() },
        (event) => {
          if (!interrupted())
            setLive((current) => ({
              ...current,
              events: [...current.events, event],
            }));
        },
        request.signal,
      );
    } catch (error) {
      if (interrupted()) return;
      failure = error instanceof Error ? error.message : String(error);
    }
    if (interrupted()) return;
    try {
      const value = await get<Conversation>(path);
      if (interrupted()) return;
      setLoaded({ id, key, value, error: "" });
      setLive({ ...blank, id, error: failure });
    } catch (error) {
      if (interrupted()) return;
      setLive((current) => ({
        ...current,
        running: false,
        error: failure || String(error),
      }));
    }
  }
  return {
    value: loaded.id === id ? loaded.value : null,
    error: loaded.id === id ? loaded.error : "",
    loading: !!id && loaded.key !== key,
    live: live.id === id ? live : blank,
    send,
    reload: () => {
      setLive(blank);
      setRevision((value) => value + 1);
    },
  };
}
