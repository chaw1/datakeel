import { useEffect, useState } from "react";

import { loadObject } from "../../api/objects";

import type { ObjectTarget } from "./navigation";
import type { ObjectData } from "../../api/objects";

export function useObject(target: ObjectTarget) {
  const [revision, setRevision] = useState(0);
  const { kind, id, datasetId, versionId } = target;
  const identity = JSON.stringify([kind, id, datasetId, versionId]);
  const key = `${identity}:${String(revision)}`;
  const [state, setState] = useState<{
    identity: string;
    key: string;
    value: ObjectData | null;
    error: string;
  }>({ identity: "", key: "", value: null, error: "" });
  useEffect(() => {
    let active = true;
    void loadObject({ kind, id, datasetId, versionId }).then(
      (value) => {
        if (active) setState({ identity, key, value, error: "" });
      },
      (error: unknown) => {
        if (active)
          setState((previous) => ({
            identity,
            key,
            value: previous.identity === identity ? previous.value : null,
            error: error instanceof Error ? error.message : String(error),
          }));
      },
    );
    return () => {
      active = false;
    };
  }, [identity, key, kind, id, datasetId, versionId]);
  return {
    value: state.identity === identity ? state.value : null,
    loading: state.key !== key,
    error: state.key === key ? state.error : "",
    reload: () => {
      setRevision((value) => value + 1);
    },
  };
}
