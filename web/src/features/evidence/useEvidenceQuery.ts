import { useEffect, useMemo, useState } from "react";

import { queryEvidence } from "../../api/evidence";

import { evidenceQuery } from "./query";

import type { EvidenceFilters } from "./query";
import type { EvidenceQueryResult } from "../../api/types";

export function useEvidenceQuery(
  datasetId: string,
  filters: EvidenceFilters,
  cursor: string | null,
  revision: number,
) {
  const query = useMemo(
    () => evidenceQuery(datasetId, filters, cursor),
    [datasetId, filters, cursor],
  );
  const key = `${JSON.stringify(query)}:${String(revision)}`;
  const invalid = filters.qualityMin > filters.qualityMax;
  const [result, setResult] = useState<{
    key: string;
    value: EvidenceQueryResult | null;
    error: string;
  }>({ key: "", value: null, error: "" });
  useEffect(() => {
    if (invalid) return;
    let active = true;
    void queryEvidence(query)
      .then((value) => {
        if (active) setResult({ key, value, error: "" });
      })
      .catch((reason: unknown) => {
        if (active)
          setResult({
            key,
            value: null,
            error: reason instanceof Error ? reason.message : String(reason),
          });
      });
    return () => {
      active = false;
    };
  }, [key, query, invalid]);
  return {
    value: result.key === key && !invalid ? result.value : null,
    error: result.key === key ? result.error : "",
    loading: !invalid && result.key !== key,
    invalid,
  };
}
