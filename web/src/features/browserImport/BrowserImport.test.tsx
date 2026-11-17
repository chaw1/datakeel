import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import * as uploads from "../../api/uploads";

import { BrowserImport } from "./BrowserImport";
import * as folder from "./folder";

function source(path: string) {
  const file = new File(["sample"], path.split("/").at(-1) ?? "unknown");
  Object.defineProperty(file, "webkitRelativePath", { value: path });
  return file;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("pairs sidecars, reports bad bytes, and keeps the declaration on a retry", async () => {
  vi.stubGlobal("createImageBitmap", (file: File) =>
    file.name === "bad.png"
      ? Promise.reject(new Error("bad image"))
      : Promise.resolve({ close: vi.fn() }),
  );
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = vi.fn(() => "blob:local-fixture");
      static revokeObjectURL = vi.fn();
    },
  );
  const prepared = vi.spyOn(folder, "prepareFolderUpload").mockResolvedValue({
    declaration: {
      idempotency_key: "fixture-folder",
      name: "images",
      filename: "image-folder.bin",
      total_bytes: 1,
      chunk_bytes: 1,
      sha256: "0".repeat(64),
    },
    payload: new Blob(["x"]),
  });
  const upload = vi
    .spyOn(uploads, "uploadFolder")
    .mockRejectedValueOnce(new Error("Temporary failure"))
    .mockResolvedValueOnce("new-dataset");
  const onDone = vi.fn();
  render(<BrowserImport onDone={onDone} onCancel={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Choose image folder"), {
    target: {
      files: [
        source("images/test/source.png"),
        source("images/test/source.annotations.json"),
        source("images/bad.png"),
      ],
    },
  });
  expect(await screen.findByText("test/source.png")).toBeVisible();
  expect(
    screen.getByText("Annotation · test/source.annotations.json"),
  ).toBeVisible();
  expect(screen.getByText("train/bad.png")).toBeVisible();
  expect(
    screen.getByRole("checkbox", { name: "Skip unreadable images (1)" }),
  ).toBeChecked();
  const button = screen.getByRole("button", { name: "Import dataset" });
  fireEvent.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Temporary failure",
  );
  fireEvent.click(button);
  await waitFor(() => {
    expect(onDone).toHaveBeenCalledWith("new-dataset");
  });
  expect(prepared).toHaveBeenCalledOnce();
  expect(prepared.mock.calls[0]?.[1].map(({ path }) => path)).toEqual([
    "test/source.png",
  ]);
  expect(upload.mock.calls[1]?.[0]).toBe(upload.mock.calls[0]?.[0]);
});
