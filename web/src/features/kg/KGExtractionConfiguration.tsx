import { ResourceState } from "../../components/ResourceState";
import { useResource } from "../../lib/useResource";

import { KGExtractionForm } from "./KGExtractionForm";

import type {
  KGProfile,
  KGSchema,
  KGTranscriptionProfile,
  KGTranscriptionSelection,
} from "../../api/kg";
import type { LineageTarget } from "../../app/navigation";

export function KGExtractionConfiguration({
  datasetId,
  versionId,
  schemas,
  onChanged,
  onOpenReceipt,
}: {
  datasetId: string;
  versionId: string;
  schemas: KGSchema[];
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const profiles = useResource<KGProfile[]>("/api/kg/profiles");
  const transcriptions = useResource<KGTranscriptionProfile[]>(
    "/api/kg/transcription-profiles",
  );
  const selection = useResource<KGTranscriptionSelection>(
    versionId
      ? `/api/kg/transcription-selection?${new URLSearchParams({ dataset_id: datasetId, version_id: versionId })}`
      : null,
  );
  return (
    <>
      <ResourceState {...profiles} onRetry={profiles.reload} />
      <ResourceState {...transcriptions} onRetry={transcriptions.reload} />
      <ResourceState {...selection} onRetry={selection.reload} />
      <KGExtractionForm
        key={`${datasetId}:${versionId}`}
        datasetId={datasetId}
        versionId={versionId}
        schemas={schemas}
        profiles={profiles.value ?? []}
        transcriptionProfiles={transcriptions.value ?? []}
        transcriptionSelection={selection.value}
        selectionPending={selection.loading || !!selection.error}
        onChanged={onChanged}
        onOpenReceipt={onOpenReceipt}
      />
    </>
  );
}
