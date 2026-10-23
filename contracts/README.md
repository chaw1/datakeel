# Contracts

`semantic/file-semantics.yaml` is the semantic source of truth. It contains 40 format codes, 213 suffixes, modality and role vocabularies, containers and prioritized role rules. JSON syntax is used as a YAML subset. The local JSON Schema validates the source; runtime checks additionally reject duplicate codes, suffixes and alias cycles.

```sh
uv run python scripts/generate_semantic.py
uv run pytest tests/semantic
```

The generator writes the packaged Python snapshot and TypeScript snapshot in `datakeel/semantic/`. Runtime classification works from an installed wheel without locating the source checkout.

The 211 golden cases preserve format, role, confidence and conflict expectations from the reusable contract. Environment notes and original case IDs were removed, observed filenames were replaced with synthetic names, and fields describing legacy consumers' ability to open files were excluded from this platform's semantic scope. `golden-divergences.json` is empty. No remote reference system is needed to regenerate or test these artifacts.

`operators.json` is an inspectable snapshot of the 11 registered operator manifests. The authoritative definitions are each operator's Pydantic parameter model and registry entry. Tests detect drift between this snapshot and `datakeel.operators.manifests()`; no independently maintained second parameter schema exists.

A custom pipeline has `nodes`, `outputs` and optional `max_workers`. Every node has a unique `id`, named `inputs`, optional `params`, and either an `operator` ID or a control `kind` (`condition` or `route`). References use `node.slot`; the external input is `$input.files`. Condition nodes select `true` or `false` by `min_count` / `max_count` and retain the incoming slot type. Routes expose `image`, `text` and `other`. All parameter models, slot types, references and cycles are validated before execution; nodes in the same topological layer run concurrently. Operator completion callbacks run on the caller thread.

```json
{
  "nodes": [
    {"id": "route", "kind": "route", "inputs": {"files": "$input.files"}},
    {"id": "resize", "operator": "image.resize", "inputs": {"files": "route.image"}, "params": {"width": 256, "height": 256}}
  ],
  "outputs": ["resize.files", "route.text", "route.other"]
}
```

The default pipeline runs all 11 operators, a condition and a modality route. Text approximate deduplication uses normalized token Jaccard similarity. Deduplication covers the files passed to one pipeline invocation; callers that split data across independent tasks must use a final dataset-wide deduplication pass when global uniqueness is required. Privacy redaction is a configurable email/phone baseline, not a comprehensive sensitive-data detector.

Image processing accepts at most 16,000,000 pixels and 64 MiB of encoded input per file. Headers and file size are checked before pixel decoding; resize bounding boxes must satisfy the same pixel limit before execution. Hash deduplication streams file contents. Image outputs carry their actual dimensions and format; previous image/text measurements are invalidated when bytes change. Quality nodes retain the original measurements in each execution event's `quality.measurements` map.

An unselected condition or route branch passes an empty batch. Its operators complete with zero input/output counts, produce no files, and emit a normal event. This keeps execution accounting deterministic even when a dataset has only one supported modality; no file crosses an unselected branch.
