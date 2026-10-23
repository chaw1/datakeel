export interface ServerSentFrame {
  event: string;
  data: string;
  id?: string;
}

export async function* readServerSentEvents(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<ServerSentFrame> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "message";
  let data: string[] = [];
  let id: string | undefined;
  try {
    let ended = false;
    while (!ended) {
      const chunk = await reader.read();
      ended = chunk.done;
      buffer += decoder.decode(chunk.value, { stream: !ended });
      let newline = buffer.search(/[\r\n]/);
      while (newline >= 0) {
        if (!ended && buffer[newline] === "\r" && newline === buffer.length - 1)
          break;
        const line = buffer.slice(0, newline);
        const length = buffer.slice(newline, newline + 2) === "\r\n" ? 2 : 1;
        buffer = buffer.slice(newline + length);
        if (line === "") {
          if (data.length) yield { event, data: data.join("\n"), id };
          event = "message";
          data = [];
        } else if (!line.startsWith(":")) {
          const separator = line.indexOf(":");
          const field = separator < 0 ? line : line.slice(0, separator);
          let value = separator < 0 ? "" : line.slice(separator + 1);
          if (value.startsWith(" ")) value = value.slice(1);
          if (field === "event") event = value;
          if (field === "data") data.push(value);
          if (field === "id" && !value.includes("\0")) id = value;
        }
        newline = buffer.search(/[\r\n]/);
      }
    }
  } finally {
    reader.releaseLock();
  }
}
