import { useEffect } from "react";

import { get } from "../api/client";
import { objectHref } from "../features/object/navigation";

import { replaceRoute } from "./routing";

import type { Route } from "./routing";
import type { components } from "../api/generated";

export function useLegacyRoute(route: Route) {
  useEffect(() => {
    if (route.redirect) {
      replaceRoute(route.redirect);
      return;
    }
    if (!route.legacy) return;
    const state = { active: true };
    const isActive = () => state.active;
    const target = route.legacy;
    const id = target.assetId || target.datasetId;
    if (!id) {
      replaceRoute("#/datasets");
      return;
    }
    void get<components["schemas"]["SearchResult"][]>(
      `/api/search?${new URLSearchParams({ q: id, limit: "20" }).toString()}`,
    )
      .then(async (results) => {
        if (!isActive()) return;
        const item = results.find((result) => result.id === id);
        if (item)
          replaceRoute(
            objectHref({
              kind: item.kind,
              id: item.id,
              datasetId: item.dataset_id ?? undefined,
              versionId: item.version_id ?? undefined,
              tab: "relations",
              eventId: target.eventId,
            }),
          );
        else if (target.datasetId) {
          const datasets = await get<components["schemas"]["SearchResult"][]>(
            `/api/search?${new URLSearchParams({ q: target.datasetId, limit: "20" }).toString()}`,
          );
          if (!isActive()) return;
          replaceRoute(
            datasets.some(
              (item) => item.kind === "dataset" && item.id === target.datasetId,
            )
              ? objectHref({
                  kind: "dataset",
                  id: target.datasetId,
                  tab: "relations",
                  eventId: target.eventId,
                })
              : "#/datasets",
          );
        } else replaceRoute("#/datasets");
      })
      .catch(() => {
        if (isActive()) replaceRoute("#/datasets");
      });
    return () => {
      state.active = false;
    };
  }, [route]);
}
