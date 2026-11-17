import { Surface } from "../components/ui";
import { Datasheets } from "../features/datasheets/Datasheets";

import type { DatasetData } from "../api/types";

export function DatasheetsPage({
  data,
  selectedId,
}: {
  data: DatasetData;
  selectedId: string;
}) {
  return (
    <Surface as="section">
      <Datasheets
        key={selectedId}
        datasetId={selectedId}
        versions={data.versions}
      />
    </Surface>
  );
}
