# Fake vector kernel

The explicit DAG is `evidence.vector_embed` → `evidence.semantic_duplicate`,
`evidence.semantic_cluster`, `evidence.semantic_outlier` or `evidence.coverage_gap`, executed by the
existing `run_pipeline` controlled action and worker. The five-node evidence preset is unchanged.
This kernel exercises contracts with synthetic vectors. It supplies no encoder quality,
provider usage, real price or cloud latency measurements. Real egress is independently disabled
and the real budget is zero. There is no real/recording transport, credential loader or network client.
Read-only vector API and UI are described below. The [offline evaluation guide](VECTOR_OFFLINE_EVALUATION.md) describes development-only FAISS and fake-worker performance campaigns; real encoder quality remains untested.

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
changed membership and split shards are rejected. Every vector node requires one complete shard.

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

New vector publications acquire the common projection lock before reading cache producers,
predecessors or invalidations. Direct vector projection/replay, human review and rebuild use
the same lock. PostgreSQL advisory lock SQL runs once per surviving acquiring transaction:
savepoint release transfers ownership to its parent, savepoint rollback discards only its own
marker, and commit/rollback/close permits a reused Session to acquire again. The two Session
event handlers are registered once at module import, never per lock call or per Session.
SQLite uses its existing writer serialization and executes no advisory lock SQL. Ordinary
non-vector publication does not acquire this projection lock or add a lock query.

Existing task/action/source responses gain optional fake status. Complete runs report node counts,
cache hits and invented usage; failed runs expose their reason and durable attempts. Known all-input failures retain their
counts in failure audit events; global uncertainty does not invent counts for unpublished products. The read-only endpoint and interactive evidence view below consume these existing facts.

Local validation uses the repository's unchanged static gates, SQLite tests and named mutation
anchors (`vector-human-entry`, `vector-persistent-request-count`, `vector-no-redispatch`,
`vector-direct-pair`, `vector-failed-publication`), plus eligible-pair prepare/runtime and
explicit schema owner/lease anchors. Full repository coverage, PostgreSQL and
independent fresh-session acceptance remain separate validation steps.

## Set evidence

`semantic_cluster` and `semantic_outlier` accept `eps` (cosine distance, default 0.1) and
`min_samples` (including self, default 5), plus `max_samples` and `max_candidate_pairs`.
The exact precomputed F64 DBSCAN visits sorted asset IDs, includes distances equal to `eps`,
and assigns a shared border to the first cluster. Cluster IDs bind the smallest member and
configuration hash. A cluster endpoint is a versioned reference only; it does not create a
public object. Outliers are DBSCAN noise candidates, never corruption. Fewer eligible vectors
than `min_samples` produce an `insufficient` report and no outlier assertion.

`coverage_gap` accepts `reference` as a file ObjectSet, an independent cosine `threshold`,
`max_samples` and `max_reference_comparisons`. Preparation resolves every matching reference,
ignoring the ObjectSet display limit, and freezes T/R identities, revisions, original-content
hashes and separate summaries. The embedding node consumes the union T∪R once; scoring considers
T−R and exactly |T−R|×|R| comparisons. Equal nearest similarities choose the smallest reference
asset ID. Multiple versions of the same asset in R are ambiguous and rejected. All references
retain their exact immutable versions; transformed upstream payloads remain refused.

A gap assertion has a subject Whole anchor, its nearest reference Whole anchor and the complete
frozen R closure in its typed measurement. Plan reads, worker authorization, evidence reads,
assertion-source resolution and human review include every R member. Membership, revision,
content or state changes invalidate old relative candidates. Empty or partially failed R fails
the whole pending vector subgraph with a typed reason. Gap candidates describe similarity relative
to this frozen R; they do not establish absolute coverage or trigger labeling, selection or merging.

The default limits are 5000 samples and 250000 complete candidate/reference comparisons; callers
may lower them. Exceeding a bound rejects the complete result, with no top-k truncation. Per-file
T failures can retain other candidates, while global or late-node failure discards every new pending
vector product. Existing facts and settled/unknown accounting remain available.

Measurements now discriminate cosine duplicate, cluster configuration, outlier configuration and
relative coverage, replacing the earlier cosine-only boundary. All numeric measurements reject
NaN and infinity. Evidence projector 1.3 declares immutable COMPLETE bundles and append-only review
decisions as separate fact sources with a composite watermark. Compute identity binds recorded F32
vectors and full closures; fact identity additionally binds immutable outputs and decision history.
Duplicate projection diffs are no-ops; missing predecessors or stale ordering are refused. Rebuild
uses the recorded bundles, checks integrity and switches projections in one transaction. Configured
remote object storage is rejected before vector replay; no embedding transport or credential loader
is constructed. SQLite behavior is covered locally; PostgreSQL execution remains a separate check.

## Read-only vector queries / 只读向量查询

`POST /api/evidence/vector/query` reads one explicit task `run_id`. Select `kind` from
`duplicate`, `cluster`, `outlier`, or `coverage`. Optional `dataset_id` checks the run's dataset;
`subject_ids`, `statuses`, `cluster_id` and `reference_id` filter candidates. Reference filtering
matches any member of frozen R, not only the nearest member. `page_size` is 1–200 (default 20).
The stable assertion-ID order is scoped to that run. The returned `total` counts matching current
facts, including the requested review statuses.

新增接口只读取明确的任务 run。支持四类结果、来源 ID、人审状态、聚类 ID 和完整 R 成员筛选。
单页 1–200 条，默认 20 条；按该 run 的 assertion ID 稳定排序，`total` 为筛选后的当前事实数。

Send the returned `next_cursor` with exactly the same query. Signed cursors bind the run,
result/decision snapshot, complete frozen R digest, filters, page size, actor and database.
They expire after 30 minutes and are process-local: service restart or another API worker requires
pagination to restart. A rerun, review decision, R change, altered query or forged/expired cursor
returns 422 rather than mixing pages. All frozen sources, duplicate neighbors, cluster members
and R members are authorized before filtering or pagination; denial/revocation returns 403,
including requests whose filters would otherwise return no facts. Reads append no usage or
other records. SQLite uses an explicit read snapshot; PostgreSQL uses repeatable read.

后续页必须沿用完整原查询。cursor 绑定 run、事实与人审快照、完整 R 摘要、筛选、页大小、
调用身份和数据库，30 分钟过期，重启或切换 API worker 后须从首页重新查询。重跑、人审、R
变化及伪造/过期 cursor 均拒绝跨快照分页。授权在筛选前覆盖完整来源闭包；撤权直接返回 403，
不会伪装成空结果。查询不追加 usage 或其他记录。

The response distinguishes `current`, `stale`, and `unpublished` evidence from the task's typed
`success`, `partial_success`, `failed`, `cancelled`, `pending`, or `insufficient` report. An absent
operator publication is `unpublished`; empty R and failed R retain failure, never full coverage.
Complete frozen R is checked even when a successful run produced zero candidates. Superseding
publications invalidate empty historical results too. Events expose source identities, mode,
implementation and contract without raw execution parameters. Reports retain input/eligible/
failed/truncated denominators, fake usage, fake cost, and uncertain attempt reservations.

响应区分当前、失效、未发布证据，以及成功、部分成功、失败、取消、等待和样本不足状态。
零候选仍检查完整 R；空 R、参考失败和未发布结果不表示全覆盖。来源、合同、fake usage、
费用及未知 attempt 的最坏预留均可追溯，不提供真实模型质量或云端性能结论。

In Evidence, open **Vector evidence**, enter an existing task run ID, choose a kind and query.
Native form controls, review buttons and page navigation support keyboard operation. Each card
shows cosine similarity/threshold, stable cluster ID/members or DBSCAN noise, complete R/nearest
reference, anchors and producer. Human review uses the existing append-only assertion decision
action; it restarts pagination and performs no data operation. **Add gap to current selection**
rechecks the exact live assertion and adds its versioned source to the existing ObjectSet selection.
It never prepares or executes an action. A later dataset action remains a separate human choice.
All controls and explanations are available in English and Chinese.

在 Evidence 展开「向量证据」，输入已有任务 run ID，选择结果类别后查询。控件可通过键盘操作，
展示阈值、稳定聚类、噪声、R/最近参考、anchors 和 producer。人审沿用既有 append-only decide
流程并从首页重新分页，不执行数据操作。「将缺口加入当前选择」先复核该 assertion 仍有效，
再加入现有 ObjectSet；不会自动准备或执行动作，不补标、隔离或合并。
