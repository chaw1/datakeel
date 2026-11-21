import { useEffect, useRef, useState } from "react";

import { streamMessage, streamResume } from "../../api/agent";
import { get } from "../../api/client";

import type { PageContext } from "../../api/intents";
import type {
  AgentEvent,
  Conversation,
  ExecutionMode,
  MessageInput,
  ResumeInput,
} from "../../api/types";

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
function appendEvent(events: AgentEvent[], event: AgentEvent): AgentEvent[] {
  const path = event.agent_path || "main";
  const preview = (item: AgentEvent) =>
    item.event === "text_delta" && (item.agent_path || "main") === path;
  if (event.event === "text_delta") {
    const chunk = event.text;
    if (chunk === "") return events.filter((item) => !preview(item));
    if (!chunk) return events;
    if (!events.some(preview)) return [...events, event];
    return events.map((item) =>
      preview(item) ? { ...item, text: `${item.text ?? ""}${chunk}` } : item,
    );
  }
  return [
    ...(["text", "stopped", "done"].includes(event.event)
      ? events.filter((item) => !preview(item))
      : events),
    event,
  ];
}
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
  const operation = useRef(0);
  const loadVersion = useRef(0);
  const scope = useRef({ id, key });
  const path = `/api/agent/conversations/${encodeURIComponent(id)}`;
  useEffect(() => {
    scope.current = { id, key };
    if (!id) return;
    let active = true;
    const version = ++loadVersion.current;
    void get<Conversation>(path)
      .then((value) => {
        if (active && version === loadVersion.current)
          setLoaded({ id, key, value, error: "" });
      })
      .catch((error: unknown) => {
        if (active && version === loadVersion.current)
          setLoaded({ id, key, value: null, error: String(error) });
      });
    return () => {
      active = false;
    };
  }, [id, key, path]);
  useEffect(
    () => () => {
      operation.current++;
      controller.current?.abort();
      controller.current = null;
      setLive(blank);
    },
    [id],
  );
  async function refresh(sequence: number, failure = "") {
    const version = ++loadVersion.current;
    const current = () =>
      operation.current === sequence && scope.current.id === id;
    try {
      const value = await get<Conversation>(path);
      if (!current()) return;
      if (version === loadVersion.current)
        setLoaded({ id, key: scope.current.key, value, error: "" });
      setLive({ ...blank, id, error: failure });
    } catch (error) {
      if (!current()) return;
      setLive((previous) => ({
        ...previous,
        events: previous.events.filter((event) => event.event !== "text_delta"),
        running: false,
        error: failure || String(error),
      }));
    }
  }
  async function run(body: MessageInput | ResumeInput) {
    if (!id || controller.current) return;
    const request = new AbortController();
    const sequence = ++operation.current;
    loadVersion.current++;
    controller.current = request;
    const current = () =>
      operation.current === sequence && !request.signal.aborted;
    const content = "content" in body ? body.content : "";
    setLive({ id, content, events: [], running: true, error: "" });
    let failure = "";
    const onEvent = (event: AgentEvent) => {
      if (current())
        setLive((previous) => ({
          ...previous,
          events: appendEvent(previous.events, event),
        }));
    };
    try {
      if ("content" in body)
        await streamMessage(id, body, onEvent, request.signal);
      else await streamResume(id, body, onEvent, request.signal);
    } catch (error) {
      if (!current()) return;
      failure = error instanceof Error ? error.message : String(error);
    }
    if (!current()) return;
    await refresh(sequence, failure);
    if (controller.current === request) controller.current = null;
  }
  function send(
    content: string,
    context?: PageContext,
    mode: ExecutionMode = "auto",
  ) {
    return run({
      content,
      context,
      mode,
      idempotency_key: crypto.randomUUID(),
    });
  }
  function resume(planId: string) {
    return run({ plan_id: planId, idempotency_key: crypto.randomUUID() });
  }
  async function stop() {
    if (!controller.current) return;
    controller.current.abort();
    controller.current = null;
    const sequence = ++operation.current;
    setLive((current) => ({
      ...current,
      events: current.events.filter((event) => event.event !== "text_delta"),
      running: false,
    }));
    await refresh(sequence);
  }
  return {
    value: loaded.id === id ? loaded.value : null,
    error: loaded.id === id ? loaded.error : "",
    loading: !!id && loaded.key !== key,
    live: live.id === id ? live : blank,
    send,
    resume,
    stop,
    reload: () => {
      setLive((current) => (current.running ? current : blank));
      setRevision((value) => value + 1);
    },
  };
}
