import { useEffect, useState } from "react";

import { get } from "../api/client";

export interface ActorIdentity {
  readonly actor: string;
  readonly zeroUsers: boolean;
  readonly scopes: readonly string[];
}

export const defaultActorIdentity: ActorIdentity = {
  actor: "local",
  zeroUsers: true,
  scopes: ["*"],
};

export function parseWorkbenchIdentity(payload: unknown): ActorIdentity | null {
  if (payload === null || typeof payload !== "object") return null;
  if (!("actor" in payload) || typeof payload.actor !== "string") return null;
  if (!("zero_users" in payload) || typeof payload.zero_users !== "boolean")
    return null;
  if (
    !("effective_scopes" in payload) ||
    payload.effective_scopes === null ||
    typeof payload.effective_scopes !== "object" ||
    !("scopes" in payload.effective_scopes) ||
    !Array.isArray(payload.effective_scopes.scopes)
  ) {
    return null;
  }
  const scopes = payload.effective_scopes.scopes.filter(
    (item): item is string => typeof item === "string",
  );
  return {
    actor: payload.actor,
    zeroUsers: payload.zero_users,
    scopes,
  };
}

export function useActorIdentity(): ActorIdentity {
  const [identity, setIdentity] = useState<ActorIdentity>(defaultActorIdentity);

  useEffect(() => {
    let active = true;
    get<unknown>("/api/production/workbench")
      .then((payload) => {
        if (!active) return;
        const parsed = parseWorkbenchIdentity(payload);
        if (parsed) setIdentity(parsed);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  return identity;
}
