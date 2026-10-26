import { ResourceState } from "../../components/ResourceState";
import { useResource } from "../../lib/useResource";
import { ReportView } from "../reports/ReportView";

import { StandardsQuality } from "./StandardsQuality";

import type { Report } from "../../api/types";

export function StandardsAnalysis() {
  const resource = useResource<Report>("/api/standards/analysis-report");
  return (
    <section className="card standards-section">
      <StandardsQuality />
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {resource.value && (
        <ReportView report={resource.value} context="standards" />
      )}
    </section>
  );
}
