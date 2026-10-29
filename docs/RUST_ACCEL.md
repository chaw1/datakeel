# Near-duplicate acceleration / 近重复加速

Datakeel keeps image decoding and the existing 64-bit dHash calculation in Python/Pillow. The optional `datakeel-accel` package accelerates integer hash comparison and normalized training-text fingerprints. Decoding and resampling differences therefore cannot change image hashes between implementations. The main Datakeel wheel stays pure Python and has no dependency on the extension.

Datakeel 保留 Python/Pillow 的图片解码与既有 64 位 dHash 计算，由可选的 `datakeel-accel` Rust 扩展加速整数哈希比较和已规范化训练文本的指纹。因此，两种实现不会因解码、缩放差异产生不同图片哈希。Datakeel 主包仍是纯 Python wheel，不依赖扩展。

## Training-text fingerprints / 训练文本指纹

Training-data duplicate indexing selects the fingerprint implementation once when opening its
disk index. Unicode normalization and case folding remain in Python. Rust receives the normalized
text, deduplicates character trigrams, selects the first 512 features in lexical order, and computes
the same eight-byte BLAKE2b hashes, 64-bit SimHash, and eight MinHash bands as the Python fallback.
Unsigned arithmetic wraps at 64 bits; half-vote SimHash ties remain set. Bands keep their original
offset byte and little-endian integer representation. Empty and short strings retain one feature.
The two implementations must return identical fingerprint bits and band bytes.

Long-text similarity can reuse exact packed trigram sets. Three Unicode scalar values occupy
21 bits each in one unsigned 64-bit value, so this representation has no feature-hash collisions.
Sorted unique values are packed as little-endian bytes; the Dice kernel counts their exact
intersection and preserves Python's floating-point result. Each disk index retains at most 4096
packed sets for texts of at most 4096 characters; larger texts bypass that cache. Texts of at most
256 characters keep the original Python edit-confirmation path. Fingerprint feature hashes use
a separate thread-local cache with at most 65536 entries; clearing a full cache changes no hash.

训练数据去重索引在打开磁盘索引时只选择一次指纹实现。Unicode 规范化和大小写折叠仍在
Python 中完成。Rust 接收规范化后的文本，去重字符三元组，按词典序选前 512 个特征，计算与
Python 回退逐位一致的八字节 BLAKE2b、64 位 SimHash 和八组 MinHash 带。无符号计算按 64 位
回绕，SimHash 票数相等时保留置位，带保留原偏移字节和小端整数编码。空文本和短文本仍有
一个特征。两种实现的指纹位和索引带字节必须完全一致。

长文本相似度可复用精确的三元组集合：每个 Unicode 码点占 21 位，三个码点无碰撞地打包为
一个64位无符号值，排序去重后保存为小端字节。Dice 内核精确计数交集，浮点结果与 Python
保持一致。每个磁盘索引最多缓存4096组、每组文本至多4096字符；更长文本绕过缓存。至多
256字符的文本仍走原 Python 编辑确认路径。指纹特征摘要另有每线程最多65536项的缓存，
缓存满后清空不改变任何摘要。

The existing `DATAKEEL_ACCEL` setting also selects this kernel. In `auto`, an absent extension or
an older installation without the selected training kernels uses Python. `off` always uses Python;
`required` reports a clear installation error when the training kernel is unavailable. The optional
extension's BLAKE2b dependency stays in `accel/` and is included in its locked license audit and
distributed upstream notices. No Python runtime dependency is added.

既有 `DATAKEEL_ACCEL` 配置也控制该内核。`auto` 在扩展缺失或旧安装缺少
所需训练内核时回退 Python；`off` 始终使用 Python；`required` 在训练内核不可用时
明确报告安装错误。可选扩展的 BLAKE2b 依赖只存在于 `accel/`，纳入锁定依赖许可审计及随包
分发的上游声明，不增加 Python 运行依赖。

## Modes / 比较模式

| Mode / 模式 | Behavior / 行为 | Tradeoff / 取舍 |
| --- | --- | --- |
| `prefix` (default / 默认) | Compare within the same four-bit prefix bucket. / 仅比较前 4 位相同的哈希。 | Preserves the existing candidate selection; cross-prefix pairs can be missed. / 保持原有候选选择，会漏掉跨前缀样本对。 |
| `exact` | Index `threshold + 1` disjoint segments; verify full Hamming distance. / 按 `threshold + 1` 个不重叠段建索引，再核对完整汉明距离。 | Finds every pair within the threshold, using additional index memory. / 找全阈值内的样本对，增加索引内存。 |

At the standard threshold of eight, nine segments cover all 64 bits. Any qualifying pair must share at least one complete segment: otherwise every segment would contain a differing bit, giving a distance of at least nine. Candidate matches are deduplicated and verified. At threshold 64, every pair qualifies and exact mode enumerates all pairs directly. Both modes return deterministic direct pairs and distances, with no transitive expansion or merging. Their runtime and output size depend on the hash distribution; an all-identical input has quadratically many true pairs.

默认阈值为 8，9 段覆盖全部 64 位。阈值内的两个哈希至少有一段完全相同；否则每段至少有一位不同，距离便至少为 9。命中的候选会去重，并再次核对完整距离。阈值为 64 时所有样本对都满足条件，exact 直接枚举全部样本对。两种模式都按确定顺序返回直接样本对和距离，不做传递扩展或合并。耗时与输出规模取决于哈希分布；全相同输入本身就有平方数量的真实样本对。

The contract defaults to `prefix`; old contracts without `mode` retain that default. A pipeline can explicitly request exact mode:

合同默认为 `prefix`，旧合同省略 `mode` 时保持该默认值。也可在流水线中显式选择：

```python
from datakeel.pipeline.evidence import evidence_pipeline

pipeline = evidence_pipeline(mode="exact")
```

## Build and select / 构建与选择

Install Rust with Cargo, rustfmt and Clippy, plus the repository's normal Python development environment. From the repository root:

先安装包含 Cargo、rustfmt、Clippy 的 Rust 工具链，并准备仓库的 Python 开发环境。在仓库根目录执行：

```bash
uv sync --locked
make check-rust
uv run python -c 'import datakeel_accel; print(datakeel_accel.__version__)'
```

`make check-rust` generates license notices, builds a local abi3 extension for Python 3.12 and later in a fresh output directory, scans the exact wheel for private artifacts, and installs that build. Prebuilt multi-platform wheels and package-index publication are outside this implementation. `make check` also builds and installs the extension and runs Rust formatting, Clippy, unit tests, license checks and Python/Rust consistency tests. Cargo is required for development gates; a missing toolchain fails with installation guidance.

`make check-rust` 先生成许可声明，再在全新输出目录构建适用于 Python 3.12 及以上版本的本机 abi3 扩展，扫描准确的 wheel 是否包含私有产物，并安装本次构建；本期不提供多平台预构建 wheel 或包索引发布。`make check` 也会构建、安装扩展，并运行 Rust 格式、Clippy、单元测试、许可检查及 Python/Rust 一致性测试。开发门禁需要 Cargo；缺少工具链时会明确失败并给出安装提示。

This installation is recommended for large training datasets and the 100,000-record, 60-second
training-check target. Pure Python fallback keeps identical results; performance measurements
must report its CPU and wall times separately from the installed-extension setup.

大规模训练数据及 10 万条 60 秒训练检查目标推荐采用上述安装方式。纯 Python 回退保持结果
一致；性能测量须分别报告纯 Python 与已安装扩展两种配置的 CPU、墙钟耗时。

| `DATAKEEL_ACCEL` | Selection / 选择 |
| --- | --- |
| `auto` (default / 默认) | Rust when installed; Python otherwise. / 已安装用 Rust，否则 Python。 |
| `off` | Always Python. / 始终用 Python。 |
| `required` | Rust; fail clearly if unavailable. / 必须用 Rust，扩展不可用时明确报错。 |

The same option is exposed as `Settings.accel`. For example, `DATAKEEL_ACCEL=off uv run datakeel worker --once` forces Python in that worker. Backend selection does not change the contract or matching mode.

同一配置也可通过 `Settings.accel` 设置。例如，`DATAKEEL_ACCEL=off uv run datakeel worker --once` 让该 worker 强制使用 Python。实现选择不会修改合同或比较模式。

Operator extraction reports include `implementation` (`python` or `rust`), `implementation_version`, and `match_mode`. In an evidence evaluation JSON report, find these on the `extraction.operators` entry whose `operator` is `evidence.near_duplicate`; `near_duplicate_mode` also states the evaluated mode. Fresh comparisons record their attribution in COMPLETE lineage quality and output-file metadata, including empty results. Fully cached near-duplicate runs still validate `required` and report the backend selected for this attempt. `skipped_cached` means previously measured facts were reused; it does not mean Rust recomputed those pairs. Python kernel version and extension package version identify different implementations and need not have the same version string.

算子抽取报告包含 `implementation`（`python` 或 `rust`）、`implementation_version`、`match_mode`。证据评测 JSON 中，在 `extraction.operators` 找到 `operator` 为 `evidence.near_duplicate` 的条目；`near_duplicate_mode` 也会记录本次模式。新计算的比较在 COMPLETE 血缘质量信息及输出文件元数据中保留实现归属，包括无命中结果。近重复全部命中缓存时，仍会验证 `required` 并记录本次所选实现；`skipped_cached` 表示复用历史测量事实，不表示 Rust 重新计算过这些样本对。Python 内核版本和扩展包版本分别标识不同实现，版本号无需相同。

## Reproduce measurements / 复现测量

```bash
uv run python -m scripts.near_duplicate_benchmark --output benchmark.json
uv run datakeel eval-evidence --mode exact --json
```

The hash benchmark generates 10,000, 100,000 and 1,000,000 unsigned 64-bit hashes with seed `20261027`. Each workload plants `N / 100` disjoint near-duplicate pairs with known distances one through eight; half deliberately cross the four-bit prefix. Recall means recovered planted pairs divided by all planted pairs. Random additional true pairs may also appear. This artificial recall distribution exercises the blocking boundary; it is not an estimate for real images.

哈希基准用固定种子 `20261027` 生成 1 万、10 万、100 万个无符号 64 位哈希。每组植入 `N / 100` 对互不重叠的近重复样本，距离已知且为 1–8，其中一半刻意跨越前 4 位。召回率指找到的植入对占全部植入对的比例，随机数据也可能额外命中真实样本对。这一人工分布用于检查分桶边界，不用于估计真实图片召回率。

Every case runs in a fresh local-only process. Elapsed time covers the comparison call, including input validation, index construction, sorting and returning results; it excludes dataset generation, interpreter startup, imports and image decoding. Peak RSS is the operating system's child-process high-water resident memory, including imports, input hashes, indexes and returned pairs. The timeout is 600 seconds per case; timed-out rows have no fabricated recall. JSON contains workload/result digests and implementation versions. Completed Python and Rust results are checked for identical sorted-pair digests, and exact-mode planted recall must equal one. The process/RSS runner uses POSIX `posix_spawn` and `wait4`, as available on macOS and Linux.

每项在全新的本机进程中运行，仅传入明确的本地环境。耗时包括比较调用中的输入校验、索引构建、排序及结果返回，不包括数据生成、解释器启动、导入和图片解码。峰值 RSS 来自操作系统对子进程常驻内存的高水位统计，包含导入、输入哈希、索引和结果。每项限时 600 秒，超时项不编造召回率。JSON 保存工作负载/结果摘要及实现版本；完成的 Python 与 Rust 结果必须具有相同的有序样本对摘要，exact 植入召回率必须为一。进程/RSS 测量使用 macOS、Linux 提供的 POSIX `posix_spawn` 和 `wait4`。

## Measured hash performance / 哈希性能实测

Measured on 2026-10-27: Apple M5 Pro, 15 logical CPUs, 48 GiB RAM, macOS 26.3.2 / Darwin 25.3.0 arm64; CPython 3.12.13, Rust 1.96.0, release extension 0.1.0, Python kernel 1.0. Rust uses Rayon's default local thread pool. Each row is one measured invocation on a shared development machine with concurrent quality gates and other tasks. This is a single-sample microbenchmark, with no statistical confidence claim; these are comparison-kernel measurements, not end-to-end image-processing speedups.

测量日期 2026-10-27：Apple M5 Pro，15 个逻辑 CPU、48 GiB 内存，macOS 26.3.2 / Darwin 25.3.0 arm64；CPython 3.12.13、Rust 1.96.0、release 扩展 0.1.0、Python 内核 1.0。Rust 使用 Rayon 默认本机线程池。测试机器同时运行质量门禁和其他任务，每行均为一次真实调用。这是单次采样微基准，不宣称统计置信度；数值衡量哈希比较内核，不代表包含图片处理的整条流水线提速。

| Hashes / 哈希数 | Implementation / 实现 | Mode / 模式 | Elapsed / 秒 | Peak RSS / MiB | Planted recall / 植入召回 |
| ---: | --- | --- | ---: | ---: | ---: |
| 10,000 | Python | prefix | 0.464507 | 53.89 | 0.5 |
| 10,000 | Rust | prefix | 0.002147 | 53.88 | 0.5 |
| 10,000 | Python | exact | 2.198159 | 56.50 | 1.0 |
| 10,000 | Rust | exact | 0.004599 | 54.23 | 1.0 |
| 100,000 | Python | prefix | 26.530354 | 71.94 | 0.5 |
| 100,000 | Rust | prefix | 0.076127 | 60.80 | 0.5 |
| 100,000 | Python | exact | 156.338769 | 103.66 | 1.0 |
| 100,000 | Rust | exact | 0.074468 | 74.33 | 1.0 |
| 1,000,000 | Python | prefix | timeout / 超时 (600.041 wall s) | 236.38 | — |
| 1,000,000 | Rust | prefix | 12.815007 | 149.05 | 0.5 |
| 1,000,000 | Python | exact | timeout / 超时 (600.076 wall s) | 573.78 | — |
| 1,000,000 | Rust | exact | 7.311197 | 270.86 | 1.0 |

At 100,000 hashes, Rust prefix was **348.5×** faster than Python prefix (`26.530354 / 0.076127`). Rust exact recovered every planted pair at all three scales. Exact happened to be faster than prefix on this measured workload; data distribution and parallel execution affect the results. All completed Python/Rust mode pairs had identical result digests.

10 万哈希时，Rust prefix 比 Python prefix 快 **348.5 倍**（`26.530354 / 0.076127`）。Rust exact 在三个规模均找全植入样本对。本机此组工作负载中，exact 实测比 prefix 更快；数据分布和并行执行都会影响结果。所有已完成的 Python/Rust 同模式结果摘要均完全一致。

Both Python million-hash attempts were terminated at the actual 600-second process-wall limit; their table durations are observed total wall seconds, with measured RSS and no recall. Those workers were launched before the import-timing cleanup; the Python comparison algorithm was unchanged. All completed rows above use the corrected timing boundary.

Python 两项百万哈希尝试均在真实 600 秒进程时限结束时被终止；表中列出实际总 wall 耗时和实测 RSS，不填写召回率。这两个 worker 在导入计时清理前启动，Python 比较算法未改变。其余完成项均使用修正后的计时边界。

## Evidence evaluation / 证据评测

On the generated 1,000-image evidence corpus, the default prefix mode recovered 48/52 direct pairs and 47/51 validation-to-training pairs. Exact mode recovered 52/52 and 51/51, with precision and recall both 1.0. Evidence macro precision/recall also reached 1.0 in exact mode; prefix macro precision was 1.0 and recall 0.989542. Both evaluations run the actual extraction DAG and query contracts, with the same independently generated gold. The evaluation subprocess deliberately discards inherited service/configuration variables; it uses `auto` backend selection in its isolated environment and records the actual implementation.

在生成的 1,000 张图片证据集上，默认 prefix 模式找到了 48/52 对直接样本、47/51 对 val→train 样本。exact 找到了 52/52 和 51/51，两类 precision、recall 均为 1.0。exact 证据宏平均 precision、recall 同样为 1.0；prefix 宏平均 precision 为 1.0、recall 为 0.989542。两次评测都执行真实抽取 DAG 和查询合同，对照同一份独立生成的 gold。评测子进程会清除继承的服务/配置变量，在隔离环境里使用 `auto` 选择实现并记录实际归属。
