import { expect, it, vi } from "vitest";

import { ApiError, get } from "./client";
it("normalizes API error details in the shared request boundary", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Dataset not found" }), {
          status: 404,
        }),
      ),
    ),
  );
  await expect(get("/api/datasets/missing")).rejects.toEqual(
    new ApiError(404, "404 Dataset not found"),
  );
});
