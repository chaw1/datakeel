import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import {
  getProjectWorkbench,
  getTaskWorkbench,
  getWorkbench,
} from "../../api/production";

import { correctedView } from "./model";
import { pageQuery, taskNavigation } from "./paging";
import { TaskPrefetchCache } from "./session/TaskPrefetchCache";
import {
  readWorkspaceSnapshot,
  writeWorkspaceSnapshot,
  clearWorkspaceSnapshot,
} from "./session/workspaceSnapshot";
import { useNavigationQueue } from "./useNavigationQueue";

import type { WorkbenchView } from "./model";
import type {
  ProjectWorkbench,
  TaskWorkbench,
  WorkbenchIndex,
} from "../../api/production";

export function useLabelingWorkspace(params: URLSearchParams) {
  const requestedProject = params.get("project") ?? "";
  const requested = useRef(requestedProject);
  const [boot] = useState(() => {
    const stored = readWorkspaceSnapshot();
    return stored &&
      requestedProject &&
      stored.project?.project.id !== requestedProject
      ? { ...stored, project: null, task: null }
      : stored;
  });
  const [verified, setVerified] = useState(false);
  const identityVerified = useRef(false);
  const identityEpoch = useRef(0);
  const isIdentityVerified = useCallback(() => identityVerified.current, []);
  const verificationRetries = useRef(0);
  const verifiedActor = useRef(boot?.index.actor ?? null);
  const [identityRefresh, setIdentityRefresh] = useState(0);
  const [index, setIndex] = useState<WorkbenchIndex | null>(
    boot?.index ?? null,
  );
  const [projectId, setProjectId] = useState(
    params.get("project") ?? boot?.project?.project.id ?? "",
  );
  const [view, setView] = useState<WorkbenchView>(() =>
    boot?.project
      ? correctedView(
          "data",
          boot.project.project.workflow_tier === "personal",
          boot.project.effective_scopes,
        )
      : "data",
  );
  const [project, setProject] = useState<ProjectWorkbench | null>(
    boot?.project ?? null,
  );
  const [task, setTask] = useState<TaskWorkbench | null>(boot?.task ?? null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(0);
  const [packageId, setPackageId] = useState("");
  const [search, setSearch] = useState("");
  const [cursors, setCursors] = useState<string[]>([""]);
  const [refresh, setRefresh] = useState(0);
  const [notice, setNotice] = useState<"first" | "last" | null>(null);
  const guard = useRef<(() => Promise<boolean>) | null>(null);
  const sequence = useRef(0);
  const [cache] = useState(
    () =>
      new TaskPrefetchCache(getTaskWorkbench, (data) =>
        data.sample.media_type.startsWith("image/")
          ? (data.sample.image_width ?? 0) > 3000 ||
            (data.sample.image_height ?? 0) > 2000
            ? (data.sample.thumbnail_url ?? data.sample.content_url)
            : data.sample.content_url
          : null,
      ),
  );
  const registerGuard = useCallback((next: (() => Promise<boolean>) | null) => {
    guard.current = next;
  }, []);
  const changed = useCallback(() => {
    setRefresh((n) => n + 1);
  }, []);
  useEffect(() => {
    let live = true;
    const epoch = identityEpoch.current;
    let retry: ReturnType<typeof setTimeout> | undefined;
    void getWorkbench()
      .then((data) => {
        if (live && epoch === identityEpoch.current) {
          if (
            verifiedActor.current !== null &&
            verifiedActor.current !== data.actor
          ) {
            cache.clear();
            clearWorkspaceSnapshot();
            sequence.current++;
            setBusy(false);
            setTask(null);
            setProject(null);
            setView("data");
            setPackageId("");
            setSearch("");
            setPage(0);
            setCursors([""]);
            setProjectId(data.projects[0]?.id ?? "");
            setRefresh((n) => n + 1);
          }
          verifiedActor.current = data.actor;
          identityVerified.current = true;
          verificationRetries.current = 0;
          setVerified(true);
          setIndex(data);
          setProjectId((id) => id || data.projects[0]?.id || "");
        }
      })
      .catch((reason: unknown) => {
        if (live && epoch === identityEpoch.current) {
          identityVerified.current = false;
          setVerified(false);
          if (
            reason instanceof ApiError &&
            [401, 403].includes(reason.status)
          ) {
            cache.clear();
            sequence.current++;
            setVerified(false);
            setTask(null);
            setProject(null);
          }
          setError(reason instanceof Error ? reason.message : String(reason));
          if (
            reason instanceof TypeError ||
            (reason instanceof ApiError &&
              [408, 429, 502, 503, 504].includes(reason.status))
          ) {
            const delay = Math.min(
              1000 * 2 ** verificationRetries.current++,
              5000,
            );
            retry = setTimeout(() => {
              setIdentityRefresh((n) => n + 1);
            }, delay);
          }
        }
      });
    return () => {
      live = false;
      clearTimeout(retry);
    };
  }, [boot, identityRefresh, cache]);
  useEffect(() => {
    if (!projectId) return;
    let live = true;
    void getProjectWorkbench(
      projectId,
      pageQuery(view, packageId, cursors[page] ?? "", search),
    )
      .then((data) => {
        if (
          live &&
          (verifiedActor.current === null ||
            data.effective_scopes.actor === verifiedActor.current)
        ) {
          setProject(data);
          setError("");
          const usable = correctedView(
            view,
            data.project.workflow_tier === "personal",
            data.effective_scopes,
          );
          if (usable !== view) setView(usable);
        }
      })
      .catch((reason: unknown) => {
        if (live) {
          if (
            reason instanceof ApiError &&
            [401, 403].includes(reason.status)
          ) {
            cache.clear();
            sequence.current++;
            setTask(null);
            setProject(null);
          }
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      });
    return () => {
      live = false;
    };
  }, [projectId, refresh, view, page, cursors, packageId, search, cache]);
  const edges = taskNavigation(project, task, page);
  const navigation = { previous: edges.previous, next: edges.next };
  async function mayLeave() {
    return !guard.current || (await guard.current());
  }
  async function openTask(taskId: string): Promise<TaskWorkbench | null> {
    if (!(await mayLeave())) return null;
    const request = ++sequence.current;
    setError("");
    const cached = cache.peek(taskId);
    if (cached) {
      setBusy(false);
      setTask(cached);
      return cached;
    }
    setBusy(true);
    try {
      const loaded = await cache.get(taskId);
      if (request !== sequence.current) return null;
      setTask(loaded);
      return loaded;
    } catch (reason) {
      if (request === sequence.current)
        setError(reason instanceof Error ? reason.message : String(reason));
      return null;
    } finally {
      if (request === sequence.current) setBusy(false);
    }
  }
  useEffect(() => {
    if (!task || !project) return;
    const ids = project.tasks.map((item) => item.id);
    cache.prefetch(ids, ids.indexOf(task.task.id));
  }, [task, project, cache]);
  const receiveTask = useCallback(
    (next: TaskWorkbench) => {
      if (!index || verifiedActor.current !== index.actor) return;
      cache.set(next.task.id, next);
      if (task?.task.id === next.task.id && project)
        writeWorkspaceSnapshot({ index, project, task: next });
      setTask((current) => {
        if (current?.task.id !== next.task.id) return current;
        return next;
      });
    },
    [cache, index, project, task?.task.id],
  );
  const selectProject = useCallback(async (id: string) => {
    if (guard.current && !(await guard.current())) return;
    sequence.current++;
    setTask(null);
    setProject(null);
    setProjectId(id);
    setPage(0);
    setCursors([""]);
    setView("data");
    setPackageId("");
    setSearch("");
  }, []);
  useEffect(() => {
    if (requested.current === requestedProject) return;
    requested.current = requestedProject;
    if (requestedProject) void selectProject(requestedProject);
  }, [requestedProject, selectProject]);
  async function selectPackage(id: string) {
    if (id === packageId || !(await mayLeave())) return;
    sequence.current++;
    setTask(null);
    setPackageId(id);
    setPage(0);
    setCursors([""]);
  }
  function searchTasks(text: string) {
    sequence.current++;
    setSearch(text);
    setPage(0);
    setCursors([""]);
  }
  async function selectView(next: WorkbenchView) {
    if (await mayLeave()) {
      sequence.current++;
      setTask(null);
      setView(next);
      setPage(0);
      setCursors([""]);
    }
  }
  async function open(taskId: string) {
    await openTask(taskId);
  }
  const navigate = useNavigationQueue(
    { project, task, page, cursors },
    {
      mayLeave,
      open: openTask,
      close: () => {
        sequence.current++;
        setTask(null);
      },
      setNotice,
      loadPage: async (target, cursor, nextCursors) => {
        const request = ++sequence.current;
        setBusy(true);
        try {
          const data = await getProjectWorkbench(
            projectId,
            pageQuery(view, packageId, cursor, search),
          );
          if (
            request !== sequence.current ||
            (verifiedActor.current !== null &&
              data.effective_scopes.actor !== verifiedActor.current)
          )
            return null;
          setCursors(nextCursors);
          setPage(target);
          setProject(data);
          return data;
        } catch (reason) {
          if (request === sequence.current)
            setError(reason instanceof Error ? reason.message : String(reason));
          return null;
        } finally {
          if (request === sequence.current) setBusy(false);
        }
      },
    },
  );
  async function paginate(direction: -1 | 1) {
    if (!(await mayLeave())) return;
    if (direction === 1 && project?.next_cursor) {
      setCursors((values) => [
        ...values.slice(0, page + 1),
        project.next_cursor ?? "",
      ]);
      setPage(page + 1);
    }
    if (direction === -1 && page > 0) setPage(page - 1);
    sequence.current++;
    setTask(null);
  }
  useEffect(() => {
    const reconnect = () => {
      identityEpoch.current++;
      identityVerified.current = false;
      setVerified(false);
      setIdentityRefresh((n) => n + 1);
      setRefresh((n) => n + 1);
    };
    window.addEventListener("online", reconnect, true);
    return () => {
      window.removeEventListener("online", reconnect, true);
    };
  }, []);
  useEffect(() => {
    if (index) writeWorkspaceSnapshot({ index, project, task });
  }, [index, project, task]);
  return {
    index,
    verified,
    isIdentityVerified,
    projectId,
    project,
    task,
    error,
    busy,
    page,
    navigation,
    notice,
    packageId,
    search,
    searchTasks,
    selectPackage,
    view,
    cache,
    receiveTask,
    changed,
    registerGuard,
    open,
    selectProject,
    selectView,
    navigate,
    paginate,
  };
}
