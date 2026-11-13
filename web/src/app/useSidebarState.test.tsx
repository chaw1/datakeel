import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";

import { useSidebarState } from "./useSidebarState";

beforeEach(() => {
  localStorage.clear();
  window.location.hash = "#/workbench";
});

it("defaults to expanded sidebar and groups, and persists rail toggle", () => {
  const { result } = renderHook(() => useSidebarState());
  expect(result.current.collapsed).toBe(false);
  expect(result.current.collapsedGroups).toEqual([]);

  act(() => {
    result.current.toggleCollapsed();
  });
  expect(result.current.collapsed).toBe(true);
  expect(localStorage.getItem("datakeel.sidebar.collapsed")).toBe("1");

  act(() => {
    result.current.toggleCollapsed();
  });
  expect(result.current.collapsed).toBe(false);
  expect(localStorage.getItem("datakeel.sidebar.collapsed")).toBeNull();
});

it("toggles rail with Ctrl+B / Meta+B unless focus is inside an editable field", () => {
  const { result } = renderHook(() => useSidebarState());

  act(() => {
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "b", ctrlKey: true }),
    );
  });
  expect(result.current.collapsed).toBe(true);

  const input = document.createElement("input");
  document.body.appendChild(input);
  act(() => {
    input.dispatchEvent(
      new KeyboardEvent("keydown", { key: "b", metaKey: true, bubbles: true }),
    );
  });
  expect(result.current.collapsed).toBe(true);
  input.remove();

  act(() => {
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "b", metaKey: true }),
    );
  });
  expect(result.current.collapsed).toBe(false);
});

it("persists collapsed groups and auto-expands the group of a navigated route", () => {
  const { result } = renderHook(() => useSidebarState());

  act(() => {
    result.current.toggleGroup("dataGroup");
    result.current.toggleGroup("agentsGroup");
  });
  expect(result.current.collapsedGroups).toEqual(["dataGroup", "agentsGroup"]);
  expect(localStorage.getItem("datakeel.sidebar.groups")).toBe(
    JSON.stringify(["dataGroup", "agentsGroup"]),
  );

  act(() => {
    window.location.hash = "#/catalog";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(result.current.collapsedGroups).toEqual(["agentsGroup"]);
  expect(localStorage.getItem("datakeel.sidebar.groups")).toBe(
    JSON.stringify(["agentsGroup"]),
  );
});
