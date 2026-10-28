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
    <section className="card">
      <Datasheets
        key={selectedId}
        datasetId={selectedId}
        versions={data.versions}
      />
    </section>
  );
}
