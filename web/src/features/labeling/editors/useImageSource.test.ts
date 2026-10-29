import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { useImageSource } from "./useImageSource";

function fakeImages() {
  const instances: ControlledImage[] = [];
  class ControlledImage {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    src = "";
    decoding = "";
    constructor() {
      instances.push(this);
    }
  }
  vi.stubGlobal("Image", ControlledImage);
  return instances;
}
it("allows an annotation with no image", () => {
  const { result } = renderHook(() => useImageSource());
  expect(result.current).toEqual({
    image: undefined,
    loading: false,
    failed: false,
  });
});
it("loads the thumbnail first and ignores images from a previous source", () => {
  const images = fakeImages();
  const { result, rerender } = renderHook(
    ({ source, thumbnail }) => useImageSource(source, thumbnail),
    {
      initialProps: {
        source: "/full-8000x6000.png",
        thumbnail: "/preview.png",
      },
    },
  );
  expect(images.map((image) => image.src)).toEqual(["/preview.png"]);
  act(() => {
    images.at(0)?.onload?.();
  });
  expect(result.current.image?.src).toBe("/preview.png");
  expect(result.current.loading).toBe(true);
  expect(images.map((image) => image.src)).toEqual([
    "/preview.png",
    "/full-8000x6000.png",
  ]);
  const staleFullLoad = images.at(1)?.onload;
  rerender({ source: "/next.png", thumbnail: "/next-preview.png" });
  act(() => {
    staleFullLoad?.();
  });
  expect(result.current.image).toBeUndefined();
  act(() => {
    images.at(2)?.onload?.();
    images.at(3)?.onload?.();
  });
  expect(result.current.image?.src).toBe("/next.png");
  expect(result.current.loading).toBe(false);
});
it("falls back to full resolution after a preview error and retries after reconnect", () => {
  const images = fakeImages();
  const { result } = renderHook(() =>
    useImageSource("/full.png", "/preview.png"),
  );
  act(() => {
    images.at(0)?.onerror?.();
  });
  expect(images.at(1)?.src).toBe("/full.png");
  act(() => {
    images.at(1)?.onerror?.();
  });
  expect(result.current.failed).toBe(true);
  act(() => {
    window.dispatchEvent(new Event("online"));
  });
  expect(images.at(2)?.src).toBe("/preview.png");
  act(() => {
    images.at(2)?.onerror?.();
    images.at(3)?.onload?.();
  });
  expect(result.current.image?.src).toBe("/full.png");
  expect(result.current.failed).toBe(false);
});
it("does not start an old full request after the task changes while preview is loading", () => {
  const images = fakeImages();
  const { result, rerender } = renderHook(
    ({ source }) => useImageSource(source, "/shared-preview.png"),
    { initialProps: { source: "/old.png" } },
  );
  const stalePreviewLoad = images.at(0)?.onload;
  rerender({ source: "/new.png" });
  act(() => {
    stalePreviewLoad?.();
  });
  expect(images.map((image) => image.src)).toEqual([
    "/shared-preview.png",
    "/shared-preview.png",
  ]);
  expect(result.current.image).toBeUndefined();
});
