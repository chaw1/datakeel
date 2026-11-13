import type { PageContext } from "../../api/intents";
import type { Dataset } from "../../api/types";
import type { Route } from "../../app/routing";

export type ContextChip = {
  key: string;
  value: string;
};

export type CopilotContextSummary = {
  context: PageContext;
  chips: ContextChip[];
  datasetId: string;
};

function readParam(params: URLSearchParams, ...names: string[]): string | null {
  for (const name of names) {
    const value = params.get(name)?.trim();
    if (value) return value;
  }
  return null;
}

/** Build a typed PageContext and concise display chips from the active route and dataset selection. */
export function derivePageContext(
  route: Route,
  selectedDataset?: Dataset | null,
  objectName?: string,
): CopilotContextSummary {
  const { params } = route;
  const projectId = readParam(params, "project_id", "project");
  const packageId = readParam(params, "package_id", "package");
  const taskId = readParam(params, "task_id", "task");
  const labelSetId = readParam(params, "label_set_id", "label_set");
  const paramDataset = readParam(params, "dataset_id", "dataset");
  const paramVersion = readParam(params, "version_id", "version");

  let datasetId = paramDataset ?? selectedDataset?.id ?? null;
  let versionId = paramVersion;
  let selectedKind: PageContext["selected_kind"] = null;
  let selectedIds: string[] = [];
  let objectChip: ContextChip | null = null;

  if (route.page === "object" && route.object) {
    if (route.object.kind === "dataset") {
      datasetId = route.object.id;
    } else if (route.object.kind === "version") {
      versionId = route.object.id;
      datasetId = route.object.datasetId ?? datasetId;
    } else {
      datasetId = route.object.datasetId ?? datasetId;
      objectChip = {
        key: route.object.kind,
        value: objectName || route.object.id,
      };
      if (route.object.kind === "file") {
        selectedKind = "file";
        selectedIds = [route.object.id];
      }
    }
  }

  const context: PageContext = {
    dataset_id: datasetId,
    version_id: versionId,
    project_id: projectId,
    package_id: packageId,
    task_id: taskId,
    label_set_id: labelSetId,
    selected_kind: selectedKind,
    selected_ids: selectedIds,
  };

  const chips: ContextChip[] = [];
  if (datasetId) {
    chips.push({
      key: "dataset",
      value:
        selectedDataset?.id === datasetId
          ? selectedDataset.name
          : route.page === "object" &&
              route.object?.kind === "dataset" &&
              objectName
            ? objectName
            : datasetId,
    });
  }
  if (objectChip) {
    chips.push(objectChip);
  } else if (versionId) {
    chips.push({ key: "version", value: versionId });
  }
  if (projectId) chips.push({ key: "project", value: projectId });
  if (packageId) chips.push({ key: "package", value: packageId });
  if (taskId) chips.push({ key: "task", value: taskId });
  if (labelSetId) chips.push({ key: "label_set", value: labelSetId });
  if (!chips.length) {
    chips.push({ key: "view", value: route.page });
  }

  return {
    context,
    chips,
    datasetId: datasetId ?? "",
  };
}

/** True when at least one domain object/dataset/task/project is bound to the current view. */
export function hasMeaningfulContext(summary: CopilotContextSummary): boolean {
  const { context } = summary;
  return Boolean(
    context.dataset_id ||
    context.version_id ||
    context.project_id ||
    context.package_id ||
    context.task_id ||
    context.label_set_id ||
    context.selected_ids.length,
  );
}
