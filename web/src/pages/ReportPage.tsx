import { ReportView } from "../features/reports/ReportView";

import type { DatasetData } from "../api/types";
export function ReportPage({
  data,
}: {
  data: DatasetData;
  selectedId: string;
}) {
  return (
    <section className="card">
      <ReportView report={data.report} />
    </section>
  );
}
