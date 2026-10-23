import type { components } from "../../api/generated";
import type { Version } from "../../api/types";

type PipelineInput = Pick<
  components["schemas"]["TaskInput"],
  "dataset_id" | "version_id" | "pipeline" | "shards" | "queue"
>;

export function evidenceSource(versions: Version[], sourceVersion?: string) {
  if (sourceVersion) return versions.find((item) => item.id === sourceVersion);
  return [...versions].sort(
    (left, right) =>
      left.created_at - right.created_at || left.id.localeCompare(right.id),
  )[0];
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function sidecar(value: unknown) {
  return (
    value === undefined ||
    value === null ||
    (record(value) &&
      typeof value.path === "string" &&
      typeof value.filename === "string")
  );
}

export function supportsEvidence(version: Version) {
  const images = version.manifest.filter((file) => file.modality === "image");
  return (
    images.length > 0 &&
    images.every((file) => {
      const paired: unknown = file.metadata?.evidence_sample;
      return (
        record(paired) &&
        typeof paired.sample_key === "string" &&
        paired.sample_key.length > 0 &&
        (paired.split === "train" || paired.split === "val") &&
        sidecar(paired.caption) &&
        sidecar(paired.annotation)
      );
    })
  );
}

export function extractionInput(
  datasetId: string,
  versionId: string,
): PipelineInput {
  const extractors = [
    "image_phash",
    "caption_mentions",
    "annotation_labels",
    "label_gap",
    "near_duplicate",
  ];
  const nodes: components["schemas"]["Node"][] = [
    {
      id: "evidence_images",
      kind: "route",
      inputs: { files: "$input.files" },
      params: {},
    },
  ];
  let source = "evidence_images.image";
  for (const id of extractors) {
    nodes.push({
      id,
      kind: "operator",
      operator: `evidence.${id}`,
      inputs: { files: source },
      params: { extractor_version: "1.0" },
    });
    source = `${id}.files`;
  }
  return {
    dataset_id: datasetId,
    version_id: versionId,
    shards: 1,
    queue: "cpu",
    pipeline: { nodes, outputs: [source], max_workers: 1 },
  };
}

export const pairedImportCommand = `uv run python -m examples.generate --samples 1000 --output /tmp/datakeel-paired-input
uv run python - <<'PY'
from pathlib import Path
from datakeel.storage.database import Database
from datakeel.storage.evidence_import import import_evidence_samples

dataset = import_evidence_samples(
    Database(), "Paired input", Path("/tmp/datakeel-paired-input")
)
print(dataset.id)
PY`;
