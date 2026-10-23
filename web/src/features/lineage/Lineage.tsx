import { RelationGraph } from "../graph/RelationGraph";

import type { Graph } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export default function Lineage({
  graph,
  compact = false,
  focus,
}: {
  graph: Graph;
  compact?: boolean;
  focus?: LineageTarget;
}) {
  return <RelationGraph graph={graph} compact={compact} focus={focus} />;
}
