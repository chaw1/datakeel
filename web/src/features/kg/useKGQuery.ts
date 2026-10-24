import { useEffect, useState } from "react";

import { post } from "../../api/client";

import type { KGQuery, KGResult, KGGraph } from "../../api/kg";

type Responses = { "/api/kg/query": KGResult; "/api/kg/graph": KGGraph };

export function useKGQuery<P extends keyof Responses>(
  path: P,
  query: KGQuery,
  revision: number,
  enabled = true,
): { value: Responses[P] | null; error: string; loading: boolean } {
  const body = JSON.stringify(query);
  const key = `${path}:${body}:${String(revision)}`;
  const [result, setResult] = useState<{
    key: string;
    value: Responses[P] | null;
    error: string;
  }>({ key: "", value: null, error: "" });
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    void post<Responses[P]>(path, JSON.parse(body))
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
  }, [path, key, body, enabled]);
  return {
    value: result.key === key ? result.value : null,
    error: result.key === key ? result.error : "",
    loading: enabled && result.key !== key,
  };
}
