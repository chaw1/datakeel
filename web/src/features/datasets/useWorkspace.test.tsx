import { renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { mockApi } from "../../test/fixtures";

import { useWorkspace } from "./useWorkspace";
it("loads the dataset and associated views from the local API", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) =>
      Promise.resolve(new Response(JSON.stringify(mockApi(path)))),
    ),
  );
  const { result } = renderHook(() => useWorkspace());
  await waitFor(() => {
    expect(result.current.data.files).toHaveLength(2);
  });
  expect(result.current.selected?.name).toBe("Sample collection");
});
