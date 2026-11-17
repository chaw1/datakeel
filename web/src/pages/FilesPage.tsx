import { Surface } from "../components/ui";
import { Files } from "../features/files/Files";

import type { DatasetData } from "../api/types";

export function FilesPage({
  data,
  selectedId,
}: {
  data: DatasetData;
  selectedId: string;
}) {
  return (
    <Surface as="section">
      <Files
        key={selectedId}
        files={data.files}
        versions={data.versions}
        datasetId={selectedId}
      />
    </Surface>
  );
}
