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
    <section className="card">
      <Files
        key={selectedId}
        files={data.files}
        versions={data.versions}
        datasetId={selectedId}
      />
    </section>
  );
}
