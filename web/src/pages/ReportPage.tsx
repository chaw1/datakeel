import { Surface } from "../components/ui";
import { ReportView } from "../features/reports/ReportView";

import type { DatasetData } from "../api/types";

export function ReportPage({
  data,
}: {
  data: DatasetData;
  selectedId: string;
}) {
  return (
    <Surface as="section">
      <ReportView report={data.report} />
    </Surface>
  );
}
