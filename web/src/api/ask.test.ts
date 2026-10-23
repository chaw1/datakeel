import { expect, it, vi } from "vitest";

import { retailAnswer } from "../features/ask/testFixtures";

import { askData, replayAnswer } from "./ask";

it("posts the typed question and replays an encoded saved answer id", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(retailAnswer))),
  );
  vi.stubGlobal("fetch", fetch);
  const request = {
    question: retailAnswer.question,
    reference_instant: retailAnswer.reference_instant,
    actor: "local-user",
  };
  expect(await askData(request)).toEqual(retailAnswer);
  expect(fetch).toHaveBeenCalledWith(
    "/api/ask",
    expect.objectContaining({ method: "POST", body: JSON.stringify(request) }),
  );
  expect(await replayAnswer("answer/id")).toEqual(retailAnswer);
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/ask/answer%2Fid",
    expect.objectContaining({ method: "GET" }),
  );
});
