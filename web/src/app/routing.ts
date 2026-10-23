import { useEffect, useState } from "react";

import { objectHref, readObjectTarget } from "../features/object/navigation";

import { readLineageTarget } from "./lineageNavigation";

import type { Page, LineageTarget } from "./navigation";
import type { ObjectTarget } from "../features/object/navigation";

export type Route = {
  page: Page;
  params: URLSearchParams;
  object?: ObjectTarget;
  legacy?: LineageTarget;
  redirect?: string;
};
const pages: Page[] = [
  "workbench",
  "datasets",
  "catalog",
  "ask",
  "evidence",
  "quality",
  "approvals",
  "runs",
  "agent",
  "traces",
  "ontology",
  "workflows",
  "memory",
];
export function readRoute(): Route {
  const hash = window.location.hash;
  const object = readObjectTarget(hash);
  if (object)
    return {
      page: "object",
      params: new URLSearchParams(hash.split("?")[1]),
      object,
    };
  const legacy =
    readLineageTarget(hash) ??
    (!hash && /^\/lineage\/?$/.test(window.location.pathname)
      ? (readLineageTarget(`#lineage${window.location.search}`) ?? {})
      : undefined);
  if (legacy) return { page: "lineage", params: new URLSearchParams(), legacy };
  const [name, search = ""] = (
    hash.replace(/^#\/?/, "") ||
    window.location.pathname.replace(/^\/|\/$/g, "") + window.location.search ||
    "workbench"
  ).split("?");
  if (name === "action-runs" || name === "tasks") {
    const params = new URLSearchParams(search);
    params.set("type", name === "tasks" ? "pipeline" : "action");
    return { page: "runs", params, redirect: `#/runs?${params.toString()}` };
  }
  if (name === "report") {
    const params = new URLSearchParams(search);
    const id =
      params.get("dataset") ?? params.get("dataset_id") ?? params.get("asset");
    return {
      page: "datasets",
      params,
      redirect: id
        ? objectHref({ kind: "dataset", id, tab: "report" })
        : "#/datasets",
    };
  }
  return {
    page: pages.find((page) => page === name) ?? "datasets",
    params: new URLSearchParams(search),
  };
}
export function replaceRoute(href: string) {
  window.history.replaceState(null, "", `/${href}`);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}
export function useRoute() {
  const [route, setRoute] = useState(readRoute);
  useEffect(() => {
    const update = () => {
      if (!window.location.hash.startsWith("#chapter-")) {
        setRoute(readRoute());
        window.scrollTo({ top: 0 });
      }
    };
    window.addEventListener("hashchange", update);
    window.addEventListener("popstate", update);
    return () => {
      window.removeEventListener("hashchange", update);
      window.removeEventListener("popstate", update);
    };
  }, []);
  return route;
}
