import { post, requireSuccess } from "./client";

import type { MemoryCreate, MemoryDeletion, MemoryEntry } from "./types";

export function createMemory(body: MemoryCreate) {
  return post<MemoryEntry>("/api/agent/memories", body);
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
