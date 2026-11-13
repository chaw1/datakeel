import { useCallback, useEffect, useState } from "react";

import { findNavLocation, navGroups } from "./navigation";
import { readRoute } from "./routing";

import type { NavGroupId } from "./navigation";

const COLLAPSED_KEY = "datakeel.sidebar.collapsed";
const GROUPS_KEY = "datakeel.sidebar.groups";

const validGroupIds = new Set<string>(navGroups.map((group) => group.id));

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(collapsed: boolean): boolean {
  try {
    if (collapsed) localStorage.setItem(COLLAPSED_KEY, "1");
    else localStorage.removeItem(COLLAPSED_KEY);
  } catch {
    /* ignore storage failures */
  }
  return collapsed;
}

function readGroups(): NavGroupId[] {
  try {
    const raw = localStorage.getItem(GROUPS_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is NavGroupId =>
        typeof item === "string" && validGroupIds.has(item),
    );
  } catch {
    return [];
  }
}

function writeGroups(groups: NavGroupId[]): NavGroupId[] {
  try {
    if (groups.length) localStorage.setItem(GROUPS_KEY, JSON.stringify(groups));
    else localStorage.removeItem(GROUPS_KEY);
  } catch {
    /* ignore storage failures */
  }
  return groups;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    target.isContentEditable
  );
}

export function useSidebarState() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [collapsedGroups, setCollapsedGroups] =
    useState<NavGroupId[]>(readGroups);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((previous) => writeCollapsed(!previous));
  }, []);

  const toggleGroup = useCallback((groupId: NavGroupId) => {
    setCollapsedGroups((previous) =>
      writeGroups(
        previous.includes(groupId)
          ? previous.filter((id) => id !== groupId)
          : [...previous, groupId],
      ),
    );
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        (event.metaKey || event.ctrlKey) &&
        !event.altKey &&
        !event.shiftKey &&
        !event.isComposing &&
        event.key.toLowerCase() === "b"
      ) {
        if (isEditableTarget(event.target)) return;
        event.preventDefault();
        setCollapsed((previous) => writeCollapsed(!previous));
      }
    };
    const onRouteChange = () => {
      const route = readRoute();
      const loc = findNavLocation(route.page, route.object?.kind);
      if (!loc) return;
      setCollapsedGroups((previous) =>
        previous.includes(loc.groupId)
          ? writeGroups(previous.filter((id) => id !== loc.groupId))
          : previous,
      );
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("hashchange", onRouteChange);
    window.addEventListener("popstate", onRouteChange);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("hashchange", onRouteChange);
      window.removeEventListener("popstate", onRouteChange);
    };
  }, []);

  return { collapsed, collapsedGroups, toggleCollapsed, toggleGroup };
}
