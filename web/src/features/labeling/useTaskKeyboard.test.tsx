import { fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { expect, it, vi } from "vitest";

import { translator } from "../../i18n/context";

import { altKeyName } from "./platformKeys";
import { useTaskKeyboard } from "./useTaskKeyboard";

function Harness({ navigate }: { navigate: (direction: -1 | 1) => void }) {
  const root = useRef<HTMLDivElement>(null);
  useTaskKeyboard(root, {
    editable: true,
    save: vi.fn(),
    submit: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    navigate,
    help: vi.fn(),
  });
  return (
    <div ref={root} role="region" aria-label={translator("en")("wbNav")} />
  );
}

it("navigates with macOS Option+N/P, whose keys are a dead key and π", () => {
  const navigate = vi.fn();
  render(<Harness navigate={navigate} />);
  const region = screen.getByRole("region", { name: "Annotation workbench" });
  fireEvent.keyDown(region, { key: "Dead", code: "KeyN", altKey: true });
  expect(navigate).toHaveBeenLastCalledWith(1);
  fireEvent.keyDown(region, { key: "π", code: "KeyP", altKey: true });
  expect(navigate).toHaveBeenLastCalledWith(-1);
  fireEvent.keyDown(region, { key: "n", code: "KeyN", altKey: true });
  expect(navigate).toHaveBeenLastCalledWith(1);
  fireEvent.keyDown(region, {
    key: "Dead",
    code: "KeyN",
    altKey: true,
    metaKey: true,
  });
  fireEvent.keyDown(region, { key: "n", code: "KeyN" });
  expect(navigate).toHaveBeenCalledTimes(3);
});

it("names the navigation modifier ⌥ on Apple keyboards and Alt elsewhere", () => {
  expect(
    altKeyName({
      userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/141",
    }),
  ).toBe("⌥");
  expect(
    altKeyName({ userAgent: "", userAgentData: { platform: "macOS" } }),
  ).toBe("⌥");
  expect(
    altKeyName({ userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }),
  ).toBe("Alt");
  expect(
    altKeyName({ userAgent: "", userAgentData: { platform: "Linux" } }),
  ).toBe("Alt");
  expect(translator("en")("wbCommonKeys", { alt: "⌥" })).toContain(
    "⌥+N next · ⌥+P previous",
  );
  expect(translator("zh")("wbCommonKeys", { alt: "Alt" })).toContain(
    "Alt+N 下一条 · Alt+P 上一条",
  );
});
