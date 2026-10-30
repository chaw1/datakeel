import { useState } from "react";

import type { LocateRequest } from "./types";

/** Select the object a reviewer asked to locate, once per request, when this editor holds it. */
export function useLocate(
  kind: LocateRequest["kind"],
  request: LocateRequest | null | undefined,
  select: (index: number) => void,
) {
  const [seen, setSeen] = useState(request);
  if (request !== seen) {
    setSeen(request);
    if (request?.kind === kind) select(request.index);
  }
}
