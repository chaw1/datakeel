# Offline vector evaluation / 离线向量评测

This development-only campaign compares the existing F64 evidence algorithms with
`faiss-cpu==1.15.1` `IndexFlatIP`. It adds no product imports, runtime requirements, ANN,
API, database tables, model transports or UI behavior. It uses authored synthetic text and
handwritten vectors. Encoder semantic quality and cloud latency are **not_tested**; real spend
is **0**. Synthetic contract gold is not encoder-quality gold.

本工具只评测离线合同，不代表真实编码器质量、云端延迟或真实价格。真实语义质量和云端
latency 均为 `not_tested`，真实花费为 0。不接收语料目录或远端地址，不发现或读取其他数据集。
所有数据库、对象、源文件和派生缓存均在本次新建目录内。运行期间清除继承的服务配置和凭证
环境变量，并拒绝所有 socket 连接和 DNS。不得用此工具访问私有留出；独立验收另行保管与执行。

## Reproduce / 复跑

Provision the locked development environment first as described in [CONTRIBUTING](../CONTRIBUTING.md).
The FAISS closure is exactly FAISS 1.15.1, existing NumPy 2.5.4 and packaging 26.3. No package
installation or download occurs in the campaign itself. With the environment cached:

```sh
uv sync --locked --offline
uv run --locked --offline python -m scripts.we_e5.campaign --output artifacts/we/campaigns --assets 24 --repetitions 3
```

Run the same command again. Each invocation retains a fresh `run-*` directory; previous measurements
are not overwritten. Compare `workload_sha256` and `reproducible_facts_hash` in `campaign.json`.
They bind frozen inputs, computation facts and numerical metrics; run UUIDs and measured times
are intentionally separate. The JSON retains run/plan/task IDs, source versions, signed prepared
inputs, complete T/R, request/cache keys, recorded vectors, actual worker facts, raw per-repeat
wall time/RSS and min/median/max summaries. `raw-*.json` and every owned SQLite database remain
available for independent inspection. `workload.json` is written before the first measured action.
A failed validation exits nonzero and retains the already written raw records.

默认 seed=20261107、24 个 T、2 个独立 R、维度/数值 prefix=64、每组重复 3 个、3 个 singleton
noise、duplicate/gap threshold=0.98、DBSCAN eps=0.02/min_samples=2。完整参数、源内容、稳定 ID、
输入顺序、阶段顺序、重复次数及生成夹具时间戳均先冻结。R 含前两个组的独立资产，T/R 不重叠。
数值 prefix 只截取向量坐标；产品 worker 的文本仍保持原始 UTF-8，不做文本前缀或隐式截断。
5000 样本、250000 完整候选/参考比较上界保持原样；超限失败，不使用 top-k 逃避容量限制。

## Numerical contract / 数值口径

The handwritten oracle contains scaled orthogonal/sign axes with explicit expected duplicate
pairs, survivors, clusters, noise and nearest-reference ties. A separate comparison reads actual
committed fake-worker vectors and compares both branches against the worker's committed four
kinds of evidence. Gold groups come from the frozen synthetic construction, never from FAISS
predictions. Production F64 direct-pair, DBSCAN and coverage functions are called unchanged.

Both branches receive the same unique, asset-ID-sorted input and the same coordinate prefix.
Reject NaN/Inf/F32 overflow and zero vectors, including a zero vector after prefixing. Normalize
in F64 and round once to contiguous F32. Insert and query **identical** normalized F32 bytes in
`IndexFlatIP`, retrieving all rows. F64 reads these same F32 coordinates and accumulates cosine
using the existing production implementation. FAISS scores use the same closed cosine range;
raw unclipped F32/F64 score errors are reported separately. No epsilon reconciles decisions.
Threshold-straddling disagreements remain explicit, including differences from original worker
facts caused by normalization. Exact-score ties use the smallest asset ID, not FAISS return order.

Offline greedy processing visits targets in ascending asset-ID order. A target can be removed
only by an already **kept** representative; removed targets cannot remove later targets. Choose
the highest similarity among kept representatives, resolving exact ties by asset ID. Duplicate
threshold is inclusive (`>=`), DBSCAN distance is inclusive (`<= eps`, including self), and gap
threshold is strict (`<`). Gaps score T minus R against all R. Greedy removals are an offline
comparison view; they execute no product data operation and do not infer transitive duplicate facts.
Raw DBSCAN labels remain available for ARI/NMI, but `noise` is the product's published-outlier
view: when the valid target population is below `min_samples`, the worker and both offline backends
publish no noise, and the synthetic noise expectation for that published view is also empty.

Reports include removal P/R/F1 with counts, group survival (at least one survivor), exactly-one,
direct-pair P/R/F1, chance-adjusted ARI, arithmetic NMI, noise P/R/F1, relative gap P/R/F1 when
supported, reduction and measured numerical branch time. Unsupported gold metrics are
`not_available`. For clustering metrics, each noise point is an independent singleton. Completely
empty predicted/expected sets score 1; an otherwise undefined precision/recall denominator scores 0.
There are no invented quality or performance acceptance thresholds.

## End-to-end measurement / 端到端测量

The five-node DAG is embedding plus duplicate/cluster/outlier/gap. Every phase prepares a real
`run_pipeline` plan, consumes its explicit fixture approval, executes the action, drains the real
worker and reads committed reports. All transport responses are the existing unmodified local
fake; probes count calls/comparisons while returning original production results. The DAG worker
and FAISS OpenMP each use one worker. No live application process or server is involved.

1. **cold** starts with empty derived caches in a freshly initialized owned SQLite store.
2. **hot** replays the same explicit source version and frozen DAG. Durable attempts and observed
   fake dispatch/comparison counts are zero; every node reports full existing cache hits.
3. **incremental** creates a new source version changing only `target-00000`. Only that peer's
   embedding key changes and only one fake request occurs. All target anchors rebind to the new
   version, so all four version-bound comparison scopes recompute. R content/keys remain fixed.

Wall time uses `perf_counter` from preparation through worker completion and report readback;
fixture generation, migration, cache snapshots and report serialization are outside the timed
interval. Numerical comparison times are reported separately and never labeled end-to-end time.
RSS is `getrusage(RUSAGE_SELF).ru_maxrss`: bytes on Darwin, KiB multiplied by 1024 on Linux.
It is the **process lifetime peak**, including earlier phases and imports, not current RSS or a
precise phase increment. Each repetition uses a fresh database; the process high-water mark persists.
Environment, Python, OS/CPU, database/dialect, package versions and the command are recorded.

本地 fake worker 时间不能称为云端 latency。价格策略显式为每 token 0；保留实际虚构的
fake codepoint usage（cold/incremental 可非零，hot 为零），不把它冒充 provider token usage。
真实 provider usage 和真实花费均为 0。固定时间/RSS 断言不是验收门槛。

## Gates and licenses / 门禁与许可

```sh
uv run --locked --offline pytest tests/evaluation/test_we_e5_numeric.py tests/evaluation/test_we_e5_campaign.py tests/evaluation/test_we_e5_dependencies.py
uv run --locked --offline python -m scripts.mutate --name we-e5-index-normalization --name we-e5-hot-zero --output artifacts/we/example-mutations.json
uv build --wheel --offline --out-dir artifacts/we/wheel
uv run --locked --offline python -m scripts.we_e5.dependencies --wheel artifacts/we/wheel/datakeel-0.24.1-py3-none-any.whl
```

The development audit checks all three exact packages, installed RECORD hashes, declared license
policy, full retained upstream license/notices and native library hashes, then inspects the actual
product wheel and runtime closure. FAISS's upstream native notices include platform-specific
OpenBLAS and LLVM OpenMP terms; notices are retained with the approved exact development
installation. This adds no runtime or Rust license exception. Installed RECORD verification is
reported as such, not as an independently verified original wheel download. Upstream artifact
URLs/SHA-256 pins are retained from `uv.lock`.

The existing repository license audit remains a separate required gate, including original
compatible certifi/orjson wheels and frontend artifacts. It stays offline and fails on missing
evidence. Never fetch unrelated packages under the FAISS authorization or weaken its rules.
New tests and named assertion-only anchors are registered in the existing test/mutation catalogs,
so both existing CI stacks include them without changing the 16-job layout. Local SQLite and
selected anchors do not prove PostgreSQL, total coverage or full CI. Final independent acceptance
must run those gates; an offline contract result alone never completes W-E.
