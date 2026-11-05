# Fake vector kernel

The explicit DAG is `evidence.vector_embed` → `evidence.semantic_duplicate`, executed by the
existing `run_pipeline` controlled action and worker. The five-node evidence preset is unchanged.
This kernel exercises contracts with synthetic vectors. It supplies no encoder quality,
provider usage, real price or cloud latency measurements. Real egress is independently disabled
and the real budget is zero. There is no real/recording transport, credential loader or network client.
Clustering, outliers, coverage gaps, vector search UI and evaluation campaigns are outside this batch.

Use generated local text or images and local object storage. A configured S3 bucket is refused
before object materialization. Text requires `modality="text"` and a reviewed discrete dimension
(default 64); images require `modality="image", dimensions=1024`. Images use the E1 experimental
internal fake request shape. Text preserves exact UTF-8 without normalization or prefixing;
the fake code-point bound is explicitly unrelated to any provider tokenizer. Image preprocessing
matches E1 EXIF/RGB/PNG512 and includes the Pillow version in cache identity.

```python
from datakeel.pipeline import Node, Pipeline

pipeline = Pipeline(
    nodes=[
        Node(id="embed", operator="evidence.vector_embed", inputs={"files": "$input.files"}),
        Node(
            id="pairs",
            operator="evidence.semantic_duplicate",
            inputs={"files": "embed.files"},
            params={"threshold": 0.9},
        ),
    ],
    outputs=["pairs.files"],
    max_workers=1,
)
```

Prepare `run_pipeline` with `dataset_id`, an explicit immutable `version_id`, and this pipeline.
If the version is omitted, preparation freezes the latest version once. For a repeat of the same
source version, reuse that explicit version; a newly produced pipeline version has different
provenance even when its bytes are unchanged. The plan's `canonical_params.vector_prepared`
contains the full DAG digest, every possible conditional input, exact active branch membership,
final per-request body hashes, complete fixture HTTPS URLs and worst request/cost bounds.
The canonical pipeline itself remains in the same signed parameters. Each request contains
one asset (within the E1 batch limit of ten), preserving exact peer-independent invalidation.

All resolved vector pipelines are external for approval, including inactive branches and zero
fake price. A person signs the exact plan digest and explicitly executes it. MCP and Agent entry
points cannot approve or execute it. Direct task submission and direct registered-operator calls
are rejected. Unknown byte-changing ancestors, altered nodes/payloads, redirects, unsigned runs,
changed membership and split shards are rejected. Both vector nodes require one complete shard.

`EmbedParams.policy` freezes invented CNY nano-units, token bounds and maximum requests/cost.
Its default price is a fake unit per code point, or 100 fake image tokens; these are test values.
They cannot authorize real work. All embedding nodes in one plan use one budget policy.
Preparation conservatively includes every possible branch and cold request in the worst bound.
The persistent account belongs to that approved plan and is shared by its nodes and attempts.

The durable state machine is `RESERVED` → `SENDING` → `SETTLED` or `UNKNOWN`. Dispatch commits
`SENDING` before invoking the local fake. Missing/invalid/excess usage and uncertain outcomes
retain worst occupancy. Fencing or cancellation refunds only an attempt still in `RESERVED`,
which proves that dispatch never began. Expired vector tasks fail instead of being requeued;
the reaper never resends an attempt. Recovery of a temporary input failure requires a new human
signed plan/run. Attempt history records plan/run/lease identities, policy/content/body hashes,
request/response IDs, reservation and usage; it contains neither credentials nor raw request bodies.

The embedding cache key includes original revision, final bytes, preprocessing, full destination,
model/dimension/modality and fake contract/implementation version. It excludes peers, run IDs
and manifest versions. Cache reuse rebinds the original source anchor to the requested version.
The global key includes every target's version/content/embedding/status summary and parameters.
Fake/recording/real namespaces are separate; this implementation reads and publishes only fake.
Successful vectors are rounded to F32 little-endian, with their byte hashes recorded.

Duplicates compare exact `i<j` F64 cosine over those F32 values. They are nontransitive candidate
facts with two original-content Whole anchors and a cosine/threshold measurement. Bounds apply
to the complete input set for the sample limit (default 5000) and to actual eligible-vector
comparisons for the pair limit (default 250000). Known input failures consume no pair budget
at prepare; execution counts only valid vector endpoints. Excess capacity fails the whole run
without top-k results or truncation. Input counts always satisfy `failed + eligible = input`;
`truncated=0`. Permanent input failures remain failures on hot cache; temporary failures are
never cached. A single input failure allows partial success; no eligible input fails the run.

All vector nodes and their cache entries are pending until the whole DAG succeeds and its lease
is revalidated. Any global or last-node failure discards every new pending vector product and
output. Historical facts and actual fake accounting remain. Immutable bundles retain vectors,
failure states and direct measurements separately from disposable caches. Compute hashes exclude
run/time identities; the fact projection hash includes measurement and human decision overlays.
Replay validates bundle hashes and cache predecessor order and reads recorded outputs only.
It never constructs transport or reconstructs missing embeddings by making another call.

Existing task/action/source responses gain optional fake status. Complete runs report node counts,
cache hits and invented usage; failed runs expose their reason and durable attempts. Known all-input failures retain their
counts in failure audit events; global uncertainty does not invent counts for unpublished products. No new vector HTTP endpoint or interactive UI is added.

Local validation uses the repository's unchanged static gates, SQLite tests and named mutation
anchors (`vector-human-entry`, `vector-persistent-request-count`, `vector-no-redispatch`,
`vector-direct-pair`, `vector-failed-publication`), plus eligible-pair prepare/runtime and
explicit schema owner/lease anchors. Full repository coverage, PostgreSQL and
independent fresh-session acceptance remain separate validation steps.
