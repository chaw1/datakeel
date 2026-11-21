import { post, requireSuccess } from "./client";

import type { components } from "./generated";
import type { MemoryCreate, MemoryDeletion, MemoryEntry } from "./types";

type MemoryUpdate = components["schemas"]["MemoryUpdate"];

export function createMemory(body: MemoryCreate) {
  return post<MemoryEntry>("/api/agent/memories", body);
}
export async function updateMemory(
  id: string,
  body: MemoryUpdate,
): Promise<MemoryEntry> {
  const response = await fetch(
    `/api/agent/memories/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    },
  );
  await requireSuccess(response);
  return response.json() as Promise<MemoryEntry>;
}
export async function deleteMemory(id: string): Promise<MemoryDeletion> {
  const response = await fetch(
    `/api/agent/memories/${encodeURIComponent(id)}`,
    {
      method: "DELETE",
      headers: { Accept: "application/json" },
    },
  );
  await requireSuccess(response);
  return response.json() as Promise<MemoryDeletion>;
}
