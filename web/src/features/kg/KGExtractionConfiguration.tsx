import { ResourceState } from "../../components/ResourceState";
import { useResource } from "../../lib/useResource";

import { KGExtractionForm } from "./KGExtractionForm";

import type { KGProfile, KGSchema, KGTranscriptionProfile } from "../../api/kg";
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
  return (
    <>
      <ResourceState {...profiles} onRetry={profiles.reload} />
      <ResourceState {...transcriptions} onRetry={transcriptions.reload} />
      <KGExtractionForm
        key={`${datasetId}:${versionId}`}
        datasetId={datasetId}
        versionId={versionId}
        schemas={schemas}
        profiles={profiles.value ?? []}
        transcriptionProfiles={transcriptions.value ?? []}
        onChanged={onChanged}
        onOpenReceipt={onOpenReceipt}
      />
    </>
  );
}
