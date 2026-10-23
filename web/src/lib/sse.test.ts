import { expect, it } from "vitest";

import { readServerSentEvents } from "./sse";

function byteStream(text: string) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
      controller.close();
    },
  });
}

it("parses UTF-8 chunks, split CRLF, comments and multiline data", async () => {
  const frames = [];
  for await (const frame of readServerSentEvents(
    byteStream(
      ': keepalive\r\nid: 7\r\nevent: text\r\ndata: {"text":\r\ndata: "你好"}\r\n\r\nevent: done\ndata: {}\n\n',
    ),
  )) {
    frames.push(frame);
  }
  expect(frames).toEqual([
    { event: "text", data: '{"text":\n"你好"}', id: "7" },
    { event: "done", data: "{}", id: "7" },
  ]);
});

it("does not present an incomplete event as a completed message", async () => {
  const frames = [];
  for await (const frame of readServerSentEvents(
    byteStream('event: text\ndata: {"text":"unfinished"}'),
  )) {
    frames.push(frame);
  }
  expect(frames).toEqual([]);
});

it("propagates stream failures so the conversation can reload persisted state", async () => {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.error(new Error("Disconnected"));
    },
  });
  const iterator = readServerSentEvents(stream);
  await expect(iterator.next()).rejects.toThrow("Disconnected");
  expect(stream.locked).toBe(false);
});
