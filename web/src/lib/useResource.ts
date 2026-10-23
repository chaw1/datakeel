import { useEffect, useState } from "react";

import { get } from "../api/client";

interface Resource<T> {
  value: T | null;
  error: string;
  loading: boolean;
  reload: () => void;
}

export function useResource<T>(
  path: string | null,
  initialValue: T | null = null,
): Resource<T> {
  const [revision, setRevision] = useState(0);
  const key = `${path ?? ""}:${String(revision)}`;
  const [resource, setResource] = useState<{
    path: string;
    key: string;
    value: T | null;
    error: string;
  }>({ path: "", key: "", value: null, error: "" });
  useEffect(() => {
    if (path === null) return;
    let active = true;
    void get<T>(path)
      .then((value) => {
        if (active) setResource({ path, key, value, error: "" });
      })
      .catch((reason: unknown) => {
        if (active)
          setResource({
            path,
            key,
            value: null,
            error: reason instanceof Error ? reason.message : String(reason),
          });
      });
    return () => {
      active = false;
    };
  }, [path, key, initialValue]);
  return {
    value:
      path === null
        ? initialValue
        : resource.path === path
          ? resource.value
          : null,
    error: resource.path === path ? resource.error : "",
    loading: path !== null && resource.key !== key,
    reload: () => {
      setRevision((value) => value + 1);
    },
  };
}
