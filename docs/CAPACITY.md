# Capacity and scale workloads / 容量与规模压测

Capacity numbers are observed operating points on a shared workstation, not universal maxima.
All fixtures are synthetic and reproducible. No conversation, extraction or vision provider is
constructed. Results and profiles belong outside the checkout.

容量数字是共享工作站上的实测工作点，不是通用最大容量。全部数据由确定性规则生成，不连接
对话、抽取或视觉模型。结果 JSON 和 profile 应保存在仓库之外。

## Reproduce / 复现

Install the locked development environment with `uv sync --locked`. The scripts package adds no
runtime or development dependencies. Run any scenario independently:

使用 `uv sync --locked` 安装锁定环境。压测工具没有增加运行时或开发依赖，每个场景可单独运行：

```sh
uv run python -m scripts.scale_bench B1 --size M --stack sqlite --seed 23 \
  --output /tmp/datakeel-b1-sqlite.json
uv run python -m scripts.scale_bench B4 --size M --stack postgres --seed 23 \
  --output /tmp/datakeel-b4-postgres.json
uv run python -m scripts.scale_bench B8 --size M --stack postgres --workers 10 --think-ms 1000 \
  --output /tmp/datakeel-b8-postgres.json
uv run python -m scripts.scale_bench.smoke --verify-mutation
```

Choose B1–B8 and S/M/L. PostgreSQL requires `DATAKEEL_TEST_DATABASE_URL` supplied by an authorized
local database launcher. Only loopback hosts are accepted. Each invocation creates a random private
schema, migrates it, and drops only that schema on exit; SQLite and object files use a temporary
home removed on exit. Never point this tool at shared application data. Queue heavy runs with your
runner's load coordinator. Optional `--profile /tmp/datakeel.prof` enables cProfile and marks its
observational overhead in the result.

可选择 B1–B8 和 S/M/L。PostgreSQL 连接必须由已授权的本地数据库启动器提供
`DATAKEEL_TEST_DATABASE_URL`，仅允许回环地址。每次运行创建独立随机 schema，迁移后执行场景，
退出时只清理本次 schema；SQLite 与对象文件使用独立临时 home 并在退出时清理。不可指向共享
应用数据。重负载运行应接入执行机的负载排队器。可选 `--profile /tmp/datakeel.prof` 启用
cProfile；带 profile 的数字包含观测开销，不能与正常容量数字混用。

| Scenario / 场景 | S | M | L |
| --- | --- | --- | --- |
| B1 dataset / 数据集 | 128 tiny physical files | 100,000 tiny physical files | 1,000,000 metadata entries |
| B2 pipeline / 流水线 | 128 files, 8 workers | 100,000 files, 8 workers | 200,000 files, 8 workers |
| B3 catalog / 目录 | 20 tables, 400 columns, 100 derived links | 10,000 tables, 200,000 columns, 50,000 derived links | 20,000 tables, 400,000 columns, 100,000 derived links |
| B4 metric facts / 问数事实行 | 1,000 | SQLite 1,000,000 / PG 10,000,000 | SQLite 2,000,000 / PG 20,000,000 |
| B5 HTTP clients / HTTP 客户端 | 4 users, 2 seconds | 50 users, 300 seconds | 50 users, 300 seconds |
| B6 crash recovery / 故障恢复 | 16 tasks, 8 workers | 10,000 tasks, 8 workers | 20,000 tasks, 8 workers |
| B7 catalog graph / 目录图 | 1,000 edges | 1,000,000 edges | 2,000,000 edges |
| B8 team claims / 团队档领取 | 4 annotators, 16 tasks, 2 seconds | 50 annotators, 10,000 tasks, 600 seconds | 50 annotators, 20,000 tasks, 600 seconds |

The seed identifies logical input data; product-generated UUIDs, timestamps and temporary paths are
excluded from its recipe fingerprint. JSON records machine/stack/database versions, revision,
scale, counts, latency percentiles, errors, RSS and cleanup. Recent envelopes additionally contain
a source SHA-256, including new untracked scripts. B2 L is capped at 200,000 physical files to keep
source/object copies within the allocation budget. B3 also includes containment links.

种子固定逻辑输入数据；产品生成的 UUID、时间戳与临时路径不计入生成配方指纹。JSON 记录机器、
栈、数据库和代码版本、规模、计数、延迟分位数、错误、RSS 与清理结果；新格式还记录包括未跟踪
脚本在内的源码 SHA-256。B2 L 限为 20 万物理文件，以控制源文件和对象副本的磁盘占用；
B3 在派生血缘之外另含包含关系。

## Measurement boundary / 测量范围

B1 uses real tiny-file imports. S/M version generation uses the real prepare/execute controlled
operation. The existing ObjectSet limit is 10,000: a larger request is explicitly rejected, and M
creates a filtered 10,000-file version from the 100,000-file dataset. L measures full metadata
snapshot persistence and comparison separately. File reads use 50-entry pages, including a deep
offset, filename/modality filters, global discovery, and dataset summary reads. Legacy clients
that omit `limit` retain full-list behavior; this also applies to existing full-list UI clients.
The capacity fixtures use ASCII names. Unicode NFC/casefold correctness has regression coverage,
but its candidate fallback is not a separately measured M latency promise.

B1 执行真实极小文件导入。S/M 的版本生成走真实受控动作的准备与执行；既有 ObjectSet 上限为
1 万，因此更大的请求会明确拒绝，M 从 10 万文件中筛选 1 万生成版本。L 单独测量完整元数据
清单的持久化与对比。文件读取使用 50 条分页，覆盖深 offset、文件名和模态筛选、全局搜索及
数据集概要。未传 `limit` 的旧客户端仍读取完整列表，已有全量列表界面也保留该行为。
容量数据使用 ASCII 文件名；Unicode NFC/casefold 已有正确性回归，但其候选回退路径没有
独立的 M 档延迟承诺。

B2 uses real processes, queue leases, empty-file validation, text quality measurements and per-worker
five-dimensional scoring. Its throughput includes process startup and shutdown. B6 kills one owned
worker with SIGKILL after its real operators and before output publication. Exactly one durable
version, output, outbox and terminal event per task is checked. One retry repeats computation;
this architecture guarantees fenced publication, not exactly-once computation or arbitrary external
side effects. Scheduler, webhooks and action polling are outside these worker drain measurements.
B6 uses a one-second lease to bound recovery wait. This is a 10,000-task drain measurement,
not an hours-long memory soak or a recovery SLA for the default lease configuration.

B2 使用真实进程、队列租约、空文件检查、文本质量测量和各 worker 的五维评分，吞吐包含进程
启停成本。B6 在真实算子完成、输出发布前 SIGKILL 本次创建的一个 worker，逐项核对每个任务
仅有一个持久版本、输出、outbox 和终态事件。一次重试会重复计算；架构保证租约围栏保护下的
单次持久发布，不保证计算或任意外部副作用只执行一次。调度器、webhook 和动作轮询不计入这些
队列排空数字。
B6 使用一秒租约控制恢复等待；这是 1 万任务排空测试，不代表数小时内存稳定性测试，也不代表
默认租约配置下的恢复时限。

B3 measures production snapshot import and service-level catalog/GraphView reads. Full historical
snapshot events remain in GraphView.events; their decoding cost is included, HTTP serialization is
not. B7 measures bounded depth-five queries over the persisted catalog projection, seeded in batches;
the M fixture has degree 10 and 100,000 nodes, returning 51 nodes and 455 edges. It does not
measure ingestion, arbitrary knowledge-graph queries, unbounded fan-out or full-graph exports. Semantic overlays, collapsed graphs, unfocused graphs and metric dependency resolution
retain the complete projection path.
B7 uses a small synthetic producer event, so its timing excludes decoding a million-edge historical
snapshot. Catalog graphs with missing external endpoints also retain a complete-projection fallback.

B3 测量真实快照导入和目录、GraphView 服务层查询。GraphView.events 仍包含完整历史快照，
计入解码成本，没有计入 HTTP 序列化。B7 分批生成持久目录投影，M 使用度数 10、10 万节点，深度五返回 51 节点、455 边；不代表
图谱导入、任意知识图谱、无界扇出或整图导出。语义叠加、折叠图、无焦点图和指标依赖解析仍
使用完整投影路径。
B7 的生产者事件很小，没有计入百万边历史快照事件的解码；目录图存在缺失外部端点时也保留
完整投影回退。

B4 measures full model-free ask_data execution: parsing, metric resolution, compilation, read-only
SQL, exact sum verification and saved answer/evidence. Queries alternate an integer SUM and a
region-filtered SUM over one table and a small semantic catalog. Joins, complex metrics and large
semantic catalogs are not represented. The 20 simultaneous clients include database pool waits.
B5 uses 50 closed-loop HTTP ASGI clients for file pages, global search, dataset objects and these
same-scale metric facts. FastAPI thread-pool waits are included; TCP, TLS and proxies are not.
Its fixed-size histogram rounds up to 1 ms; overflow beyond 60 seconds is reported explicitly.

B4 测量不接模型的完整 ask_data：解析、指标解析、编译、只读 SQL、精确求和核对和问答证据
落盘。两类问题交替执行单表整数 SUM 与区域筛选 SUM，语义目录很小，不涵盖 join、复杂指标
或大语义目录；20 个同时启动的客户端包含数据库连接池等待。B5 使用 50 个闭环 HTTP ASGI
客户端，混合文件分页、全局搜索、数据集对象和同档规模的问数。包含 FastAPI 线程池等待，
不包含 TCP、TLS 和代理；固定大小直方图向上取整到 1 ms，超过 60 秒的溢出次数单独记录。

Parent RSS excludes the PostgreSQL server. B2 additionally sums worker lifetime peaks, a conservative
upper bound rather than simultaneous RSS; B6 excludes the killed process from surviving-worker RSS.
Fixtures reserve disk conservatively, refuse allocation below 10 GiB free or above 8 GiB owned data,
and check actual allocated file blocks/schema relations at phase boundaries. PostgreSQL WAL is
server overhead beyond per-schema relation totals and remains covered by physical free-space checks.

主进程 RSS 不包含 PostgreSQL 服务端。B2 另记录各 worker 生存期峰值之和，是保守上界，不是
同时驻留量；B6 的存活 worker RSS 不包含被杀进程。运行前保守预留磁盘，剩余不足 10 GiB 或
本次数据超 8 GiB 时拒绝；阶段边界检查实际文件分配块和 schema 关系大小。PostgreSQL WAL
属于 schema 关系之外的服务端开销，由物理剩余空间检查覆盖。

## Results / 实测结果

The supplied host description is Apple M5 Pro, 15 CPU cores and 48 GiB RAM. Observed runtime:
macOS 26.3.2 arm64, Python 3.12.13, SQLite 3.53.1 and PostgreSQL 17.11 in a local aarch64
Linux container. Hardware sysctl access was restricted, so the processor model and RAM are
reported rather than independently verified. Other builds and services shared the workstation.

执行机给定配置为 Apple M5 Pro、15 核、48 GiB 内存；实测运行环境为 macOS 26.3.2 arm64、
Python 3.12.13、SQLite 3.53.1，以及本机 aarch64 Linux 容器中的 PostgreSQL 17.11。
硬件 sysctl 访问受限，因此芯片型号和内存采用给定配置，并未独立读取核实。执行期间共享
工作站上另有构建和服务运行。

The result table is populated from archived normal-run JSON. Profile measurements are kept
separately for before/after diagnosis. The table below identifies the measured revision.

实测表取自归档的正常运行 JSON；带 profile 的前后诊断数字独立保存。以下表格注明测量版本。

Measurement dates (Asia/Shanghai): 2026-10-28, version 0.13.0, baseline `a48bb0f` plus the scale-workload changes.
Individual JSON envelopes retain their exact source fingerprints; some earlier diagnostic
envelopes predate that field. Public tables use normal runs and explicitly distinguish earlier
baselines from later queries. Numbers are rounded for display; thresholds use unrounded values.

测量日期（Asia/Shanghai）为 2026-10-28，版本 0.13.0，代码基于 `a48bb0f` 加本次规模压测改动。各 JSON 保留
精确源码指纹；部分较早诊断记录尚无该字段。公开表格使用正常运行，并明确区分较早基线和
后续查询复测。展示数字经过四舍五入，是否达标按原始未舍入值判断。

<!-- CAPACITY_RESULTS_START -->

| M workload / 场景 | SQLite | PostgreSQL |
| --- | --- | --- |
| B1 import / 导入 (s) | 39.55 | 43.18 |
| B1 selected version 10k / 1万文件版本 (s) | 18.82 | 18.59 |
| B1 compare 100k→10k / 对比 (s) | 9.64 | 9.81 |
| B1 first page / 首页, p95 (ms) | 154.5 | 279.3 |
| B1 offset 50k / 深分页, p95 (ms) | 255.4 | 303.6 |
| B1 filename+modality / 筛选, p95 (ms) | 514.0 | 605.4 |
| B1 global search / 全局检索, p95 (ms) | 489.0 | 187.6 |
| B1 dataset summary / 对象概要, p95 (ms) | 76.1 | 71.7 |
| B1 whole-run parent peak / 整场主进程峰值 (GiB) | 1.795 | 1.425 |
| B2 100k files / 8 workers | 18.68s; 5352.5 files/s | 23.51s; 4253.1 files/s |
| B2 parent / sum of worker lifetime peaks (MiB) | 1311.2 / 3978.8 | 944.8 / 3374.2 |
| B3 import / 导入 (s) | 94.32 | 97.06 |
| B3 search / 搜索, p95 (ms) | 70.8 | 232.8 |
| B3 object / 对象页, p95 (ms) | 0.7 | 2.7 |
| B3 depth5 upstream/downstream, p95 (ms) | 1212.0 / 1419.9 | 1378.0 / 1075.0 |
| B4 fact rows / 事实行 | 1,000,000 | 10,000,000 |
| B4 serial / 20 clients, p95 (ms) | 205.4 / 851.3 | 253.6 / 1331.4 |
| B5 50 users / 300s, p50/p95/p99 (ms) | 10014 / 22098 / 27747 | 650 / 3678 / 4173 |
| B5 errors / requests / error rate | 2 / 1373 / 0.1457% | 0 / 13024 / 0.0000% |
| B6 10k tasks / 8 workers / SIGKILL | 99.82s; 100.18 tasks/s | 99.00s; 101.01 tasks/s |
| B6 retries / lost / duplicate publications | 1 / 0 / 0 | 1 / 0 / 0 |
| B7 1m edges, depth5 p95 (ms) | 33.9 | 111.1 |

B3 rows are the acceptance rerun of the final source tree (commit `5818ba1`, after the escaped-payload detection described below) on the retained production reader, taken while two full gates and another load test shared the machine (1-minute load 12–117). The implementer's earlier quiet-machine run before that detection measured search p95 at 12.9 / 70.6 ms and depth-5 upstream/downstream at 843.1 / 946.2 and 1127.2 / 927.0 ms (SQLite / PostgreSQL). A later event-reader candidate was measured and reverted: its normal upstream/downstream p95 increased to SQLite 1011.6/1011.5 ms and PG 1255.1/1216.5 ms. Complete historical event fields remain in the response; profiling identifies their decoding as the dominant lineage cost.

B3 各行是验收时在最终源码（提交 `5818ba1`，已包含下文的转义 payload 检测）上用保留的生产读取路径复测的数字，复测时本机同时跑着两套完整门禁和另一场压测（1 分钟负载 12–117）。实现方此前在空闲机器、加入该检测之前测得搜索 p95 为 12.9 / 70.6 ms，深度 5 上游/下游为 843.1 / 946.2 与 1127.2 / 927.0 ms（SQLite / PostgreSQL）。后续候选在正常 20 次查询中，上下游 p95 退化为 SQLite 1011.6/1011.5 ms、PG 1255.1/1216.5 ms，已撤回。响应保留全部历史事件字段，profile 表明其解码是血缘查询的主要成本。

| L dataset: 1m metadata entries / 百万元数据 | SQLite | PostgreSQL |
| --- | --- | --- |
| import / snapshot / comparison (s) | 8.65 / 5.40 / 109.39 | 21.76 / 17.64 / 116.62 |
| first / deep page / search p95 (ms) | 553.1 / 880.3 / 5977.2 | 821.7 / 1032.3 / 2906.2 |
| whole-run parent peak (GiB) | 2.980 | 1.994 |

B1 M/L explicitly use the later `B1-*-stable.json` integer-key layout measurements, not the older files named `final`. B2/B6 likewise use the stable matrix. B3 uses the acceptance rerun on the final source tree under shared load. B4/B7 retain earlier normal runs and were not rerun after the later compatibility checks, stable read snapshots and catalog escaped-payload/source filtering changes; their archived source fingerprints describe those measurements, not the final entire source tree.

B1 M/L 明确采用时间较晚、整数代理键布局的 `B1-*-stable.json`，不采用名称为 `final` 的较早文件；B2/B6 同样采用 stable 矩阵。B3 采用验收时在最终源码上、负载共享下的复测。B4/B7 保留此前正常运行，没有在后续兼容标记、稳定读快照及目录特殊 payload/source 筛选修改后重测；归档源码指纹标识各自的测量代码，不等于最终整棵源码。

B5 uses only the two continued normal 300-second / 50-user runs on the frozen final source. The source fingerprint is checked before and after each run and is identical across both stacks. Earlier B5 discovery/surrogate baselines and failed diagnostics remain archived separately and are excluded from this table. SQLite returned two HTTP 500 responses on dataset-object reads; the normal-run log has no exception trace, so their cause is unproven. Both stacks exceed the one-second p95 target, and SQLite also fails the zero-error target. A separate 60-second diagnostic with the same fixture and 50 users completed 326 requests with no error, so it did not reproduce or explain the two failures; it is excluded from capacity evidence.

B5 仅使用续跑取得的最终冻结源码、正常 300 秒/50 用户两栈实测；每次前后及两栈之间的源码指纹均相同。较早 discovery/surrogate 布局基线和失败诊断继续独立归档，不用于本表。SQLite 有两次数据集对象请求返回 HTTP 500，正常运行日志没有异常堆栈，根因尚未证实。两栈都未达到 p95 一秒，SQLite 还未达到零错误。相同 fixture/50 用户的独立 60 秒诊断完成 326 次请求、零错误，没有复现或解释这两次失败；该诊断不计入容量选源。

B4 predates the source/profile envelope fields: those fields remain unavailable in its source map; the original invocation was unprofiled. L is an offline metadata persistence/comparison experiment, with no interactive-latency promise and no public million-file version action. Other L workloads are implemented but were not measured in this matrix.

B4 早于源码/profile 字段加入，选源表保留缺失值；原命令是正常运行。L 是离线元数据持久化与对比实验，不承诺交互延迟，也不代表公开动作支持一次生成百万文件版本。其他 L 场景有工具支持，本表没有其容量实测。

<!-- CAPACITY_RESULTS_END -->

### B8 team-tier claims / 团队档多人领取

B8 seeds one team-tier project (10,000 tasks in packages of 1,000, two labels, one-minute leases)
and runs virtual annotators as threads spread over spawned processes. Each annotator repeats claim,
three saves on its own revision chain, and submit, pausing 0.5–1.5 × `--think-ms` (default one
second) before each step. Every 40th claimed task is abandoned unsubmitted, so its lease expires
while two reaper processes run every two seconds. Latency is measured at the controlled-action
boundary (prepare plus execute, as the Web API and CLI call it) without HTTP. After the run B8
reads every annotation assignment back from the database: overlapping holding windows on one task
count as a duplicate claim, and each reaper records the assignments it released so a double
release is visible. Targets for 50 annotators over ten minutes: zero duplicate claims, save p95
≤ 200 ms and next-task (claim) p95 ≤ 300 ms. `--virtual-users` changes only the annotator count.

B8 生成一个团队档项目（1 万任务，每包 1000，两个标签，租约 1 分钟），虚拟标注员是分布在多个
spawn 进程里的线程。每人循环：领取、在自己的修订链上保存三次、提交；每一步前停
0.5–1.5 倍 `--think-ms`（默认 1 秒）。每领到第 40 个任务就弃置不交，让租约过期，同时两个回收
进程每 2 秒跑一次。延迟在受控动作边界测量（准备加执行，Web API 和 CLI 走的就是这条路），不含
HTTP。跑完后从数据库读回全部标注指派：同一任务的持有时间窗重叠即算重复领取；每个回收进程
记录自己收回的指派，重复收回可见。50 人、10 分钟的目标：0 重复领取、保存 p95 ≤ 200 ms、
下一条（领取）p95 ≤ 300 ms。`--virtual-users` 只改人数。

Measured 2026-10-30 (Asia/Shanghai) on the shared workstation described above with `--workers 10
--think-ms 1000`; the one-minute load average was sampled every minute beside each run. Other
worktrees ran full parallel test suites (17 processes, 10–13 of 15 cores) for most of the night,
so each run is labelled with the load it saw.

2026-10-30（Asia/Shanghai）在上文的共享工作站上实测，参数 `--workers 10 --think-ms 1000`，每次
运行旁边每分钟记录一次 1 分钟负载。当晚其他工作树大部分时间在跑全量并行测试（17 个进程，占
15 核中的 10–13 核），所以每次运行都标明当时的负载。

| B8 M, 10 minutes / 10 分钟 | PostgreSQL 50, quiet | PostgreSQL 50, shared | SQLite 50, quiet | SQLite 20, shared | SQLite 50, shared | PostgreSQL 50, quiet, FIX1 |
| --- | --- | --- | --- | --- | --- | --- |
| Commit / 提交 | `00994be` | `28953e2` | `00994be` | `00994be` | `2f23217` | `4056141` |
| 1-minute load / 1 分钟负载 | 4.7–7.8 | 8–12, then 42–108 from minute 4 | 2.0–4.5 | 13–40 | 5–8, then 24–70 | 3.9–6.9 |
| Claims / saves / submits | 7,160 / 21,480 / 7,010 | 4,963 / 14,889 / 4,863 | 7,384 / 22,152 / 7,234 | 2,936 / 8,808 / 2,876 | 6,900 / 20,700 / 6,750 | 7,161 / 21,483 / 7,011 |
| Operations/s | 58.9 | 40.7 | 60.8 | 24.1 | 56.7 | 58.9 |
| Duplicate claims / 重复领取 | 0 | 0 | 0 | 0 | 0 | 0 |
| Abandoned leases reaped / released twice / claimed again | 150 / 0 / 150 | 100 / 0 / 100 | 150 / 0 / 150 | 60 / 0 / 60 | 150 / 0 / 150 | 150 / 0 / 150 |
| Failed annotators / lease lost while working | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| next p50 / p95 / p99 (ms) | 38 / 81 / 114 | 394 / 1,285 / 1,794 | 5 / 17 / 76 | 9 / 23 / 70 | 10 / 106 / 618 | 35 / 69 / 99 |
| save p50 / p95 / p99 (ms) | 39 / 77 / 96 | 339 / 1,030 / 1,338 | 9 / 52 / 109 | 13 / 42 / 89 | 23 / 309 / 1,004 | 36 / 66 / 85 |
| submit p95 (ms) | 77 | 1,331 | 52 | 35 | 301 | 65 |
| next p95 per minute (ms) | 281, 88, 75, 67, 61, 78, 66, 67, 62, 62 | 334, 91, 115, then 1,253–1,576 | 198, then 14–17 | 98, 19, 18, 21, 22, 30, 33, 20, 33, 13 | 216, 30, 78, 82, 80, 109, 124, 224, 396, 55 | 354, 62, 69, 70, 66, 66, 65, 63, 68, 68 |
| save p95 per minute (ms) | 92, 86, 75, 67, 66, 77, 66, 64, 65, 63 | 86, 86, 110, then 1,039–1,229 | 50–55 every minute | 33, 35, 38, 42, 44, 51, 84, 35, 55, 19 | 51, 125, 186, 292, 304, 467, 407, 713, 818, 239 | 68, 62, 69, 66, 65, 65, 67, 62, 68, 64 |
| Targets met / 达标 | Yes / 是 | No / 否 | Yes / 是 | Yes / 是 | next only / 仅下一条 | Yes / 是 |

On a quiet host PostgreSQL meets every B8 target with 50 annotators: zero duplicate claims, save
p95 77 ms and next p95 81 ms, flat from minute 2 to minute 10 while the revision and assignment
tables grow (the first minute's 281 ms is all 50 annotators claiming at once). Under shared load
the same code still holds exclusivity, but latency follows the load: with 10–13 cores taken by
another test suite, PostgreSQL p95 exceeds one second. SQLite serializes writers but its calls are
in-process: 50 annotators met every target on a quiet host (save p95 52 ms), 20 met them even under
shared load, and 50 under shared load met the next-task target but not save. The documented SQLite
scale for the team tier is therefore 20 concurrent annotators on a shared host and 50 on a
dedicated one; use PostgreSQL when several workers or services share the database, and keep CPU
headroom for it.

The last column reruns the quiet PostgreSQL measurement after P29b-FIX1, where every action
takes its table locks before any task row and claims serialize per person on an advisory lock.
Throughput is unchanged (58.9 operations/s) and the tail is lower: next p95 69 ms, save p95
66 ms, flat from minute 2 (the first minute's 354 ms is again the opening burst). Per-task
actions lock `lineage_events` in ROW EXCLUSIVE mode, which does not conflict with itself, so
annotators stay concurrent.

机器空闲时，PostgreSQL 50 人达到 B8 全部目标：0 重复领取，保存 p95 77 ms、下一条 p95 81 ms，
从第 2 分钟到第 10 分钟随着修订表和指派表增长一直持平（第 1 分钟 281 ms 是 50 人同时开领）。
共享负载下同一份代码独占性照样成立，但延迟跟着负载走：另一套测试占去 10–13 核时，PostgreSQL
p95 超过 1 秒。SQLite 写入串行但调用在进程内：机器空闲时 50 人全部达标（保存 p95 52 ms），20 人
在共享负载下也达标，50 人在共享负载下下一条达标、保存不达标。因此团队档的 SQLite 文档规模是：
共享机器上同时 20 名标注员，独占机器上 50 名；多个 worker 或服务共用数据库时用 PostgreSQL，并为
它预留 CPU。

最后一列是 P29b-FIX1 之后在机器空闲时重跑的 PostgreSQL：所有动作先拿表级锁再锁任务行，领取前按人
拿 advisory lock 串行。吞吐不变（58.9 次/秒），尾部更低：下一条 p95 69 ms、保存 p95 66 ms，从第 2
分钟起持平（第 1 分钟 354 ms 仍是开场同时领取）。单任务动作对 `lineage_events` 拿的是 ROW EXCLUSIVE，
和自己不冲突，标注员之间仍然并发。

How P29b reached this point on PostgreSQL, from 60-second diagnostic pilots (50 annotators) and
earlier full runs:

P29b 在 PostgreSQL 上的调整过程（60 秒诊断试跑，50 人；以及更早的完整运行）：

| Change / 改动 | ops/s | next p95 (ms) | save p95 (ms) | Finding / 发现 |
| --- | --- | --- | --- | --- |
| Before: every action takes `LOCK TABLE datasets, lineage_events, versions, file_states` | 13.3 | 4,885 | 4,421 | All actions serialized / 全部动作串行 |
| Per-task actions skip that lock | 0.9 | — | — | 49 of 50 annotators died on deadlocks: membership bookkeeping locked the project row after the task row / 成员记录在任务行之后锁项目行，死锁 |
| Known members skip the project row lock | 54.6 | 519 | 70 | Claim sorted 10,000 rows / 领取排序全表 |
| Claim-order index `(project_id, state, priority DESC, id)` | 56.0 | 356 | 59 | Remaining tail: the opening burst / 剩余尾部是开场 50 人同时领取 |
| First 10-minute run / 第一次 10 分钟 | — | — | — | Reapers releasing several tasks per transaction deadlocked with claims on counter rows; each release now commits alone / 回收器一个事务收回多条，与领取在计数行上死锁；改为逐条提交 |
| Second 10-minute run (load 26–36) | 38.1 | 3,154 | 685 | 0 duplicates; latency followed the load (a 240-second rerun fell from 1.8 s to 245 ms next p95 as load dropped). To shorten hot-row locks, counters are now written once, sorted, at commit / 0 重复；延迟跟着负载走（240 秒复测负载下降时下一条 p95 从 1.8 秒降到 245 ms）。为缩短热点行锁，计数改为提交前按序一次写入 |
| Fourth 10-minute run (load 52–194, `00994be`) | 33.3 | 1,829 | 1,146 | 0 duplicates; another worktree's suite ran throughout. 97 tasks abandoned, the 50 whose lease expired before the end were each released once / 0 重复；全程有其他测试在跑。弃置 97 条，其中结束前到期的 50 条各收回一次 |

Each operation is still 48–54 database round trips (authorization reads repeat across the
prepare, execute and audit sessions), and PostgreSQL runs in a local VM, so CPU contention
stretches every round trip; SQLite's in-process calls degrade far less. Fewer round trips per
action is the next lever.

每个操作仍有 48–54 次数据库往返（授权读取在准备、执行、审计几个会话里重复），PostgreSQL 跑在
本机虚拟机里，CPU 争抢会拉长每一次往返；SQLite 进程内调用受影响小得多。减少每个动作的往返
次数是下一步的抓手。



## Operational limits / 使用边界

File discovery uses a rebuildable projection of public fields from each immutable version.
Its first migration backfills all historical manifest entries in one transaction; schedule that
upgrade with write downtime and disk headroom. Later startup skips this completed backfill and
its trigger DDL. Version writes maintain the projection transactionally, while quarantine and
deletion remain live overlays. A fresh maintenance transaction can call
`rebuild_file_discovery` to reconstruct it; PostgreSQL blocks dataset and version writes during that rebuild.
Surrogate integer keys preserve legal long file identities without imposing a new text-index
key limit. Discovery still scans and ranks candidates, so large histories add query work.

文件全局检索使用从各不可变版本公共字段生成的可重建投影。首次迁移在一个事务中回填全部
历史清单，应安排暂停写入的升级窗口并预留磁盘；完成后，启动时跳过该回填及其触发器 DDL。
版本写入在同一事务维护投影，隔离和删除状态仍实时叠加。可在全新的维护事务中调用
`rebuild_file_discovery` 重建，PostgreSQL 重建期间会阻止数据集和版本写入。整数主键保留合法的长文件
标识，不新增文本索引键长限制。检索仍需扫描和排序候选，大量历史版本会增加查询工作。

Legacy JSON containing escaped NUL or surrogate strings uses an exact Python JSON fallback.
Transactional dataset/version triggers and the first backfill set a schema-wide sticky marker;
maintenance rebuild clears it only after both source tables are safe. This preserves files with
ordinary names and control characters in metadata, as well as unusual names/identities. Detection
is conservative: escaped emoji pairs and literal escape text can also enable the fallback for all
file reads in that schema. The fallback loads original manifests and has no M-scale latency or
memory guarantee. NUL queries themselves also use literal Python matching.

Marker and data reads share a stable read snapshot: PostgreSQL uses REPEATABLE READ only for these
fresh read sessions; SQLite explicitly begins a WAL read transaction without reserving the writer.
An already active caller transaction retains its settings and uses Python file-page reads.

含转义 NUL 或代理字符串的旧 JSON 使用精确 Python 解码回退。数据集、版本的事务触发器和
首次回填会设置当前 schema 的持续标记；维护重建确认两张来源表均安全后才清除。普通文件名
配控制字符元数据，以及特殊文件名、标识仍可读取。检测有意保守：转义 emoji 对和字面转义
文本也可能让该 schema 的全部文件读取回退；回退会加载原始清单，没有 M 档延迟或内存承诺。
NUL 查询值本身也按字面值在 Python 中匹配。

标记与数据使用同一个稳定读快照：PG 仅为这些新建只读 session 使用 REPEATABLE READ；
SQLite 显式开启 WAL 读事务，不预占写锁。已有调用者事务保留原设置，文件分页使用 Python 回退。

Dataset summary get/list calls use the same stable snapshot and sticky marker. When the marker is
set, file counts read the original manifest in Python and exclude the exact deleted-file IDs;
private/control metadata does not pass through PostgreSQL JSON text extraction for that count.

数据集概要的单条、列表读取同样使用稳定快照和持续标记。标记开启时，在 Python 中读取原始
清单，按精确的已删除文件 ID 计数，概要统计不会把控制字符元数据送入 PG JSON 文本提取。

Catalog search and page filtering detect escaped NUL/surrogate content per stored payload.
Ordinary rows project only navigation fields; unsafe rows read and validate the original object
in Python, with a guarded SQL branch that avoids extracting any JSON text from that row.
Exact source-ID equality and Unicode search both run over this narrow stream before pagination,
so they still scan candidates. The B3 figures above include this detection/filtering work:
under shared load, search p95 went from 12.9 to 70.8 ms on SQLite and from 70.6 to 232.8 ms on
PostgreSQL. The unsafe-row fallback capacity has not been measured.

目录搜索与分页筛选逐行检测 payload 中转义的 NUL/代理字符串。普通行仅投影导航字段；特殊行
读取原始对象并在 Python 验证，通过 SQL 条件分支避开该行的 JSON 文本提取。source_id 精确
相等和 Unicode 搜索都在该窄字段流中、分页之前筛选，因此仍需扫描候选。上表 B3 数字已包含
本轮检测与筛选开销：负载共享下搜索 p95 在 SQLite 上从 12.9 升到 70.8 ms，在 PostgreSQL 上从
70.6 升到 232.8 ms；特殊行回退容量没有测量。

Use a bounded file request such as `?limit=50&offset=0`; `q` is a literal NFC/casefold substring
and `modality` is an exact filter. Deletion is applied before pagination, and authorization remains
in place. Deep offsets and many large JSON versions still require manifest expansion; pagination
bounds response/Python memory on its normal SQL path, not database work. A controlled selection can contain at most
10,000 files regardless of the separate release budget. Larger datasets need narrower selections;
increasing the budget alone does not raise the ObjectSet ceiling.

文件请求应传入 `?limit=50&offset=0`；`q` 是 NFC/casefold 归一后的字面子串，`modality` 精确
匹配。逻辑删除在分页前生效，授权检查保留。深 offset 和多个大 JSON 版本仍需要展开清单；
正常 SQL 路径的分页约束响应和 Python 内存，不意味着数据库工作量恒定。受控选择无论发布预算多大，最多
包含 1 万文件；大数据集需缩小选择范围，仅提高预算不能解除 ObjectSet 上限。

Use PostgreSQL when multiple writers/workers must make progress together or when sustained
multi-user latency matters. SQLite serializes writers, so long write transactions delay unrelated
writes; WAL does not provide concurrent writers. Upload assembly, hashing and object verification now precede the short publication transaction.
Use bounded manifests and isolated homes; do not promise production concurrency from an S smoke. Choose an
operating point from the measured tables, with memory/disk headroom, and rerun your actual workload
before adopting its latency target. A database switch does not remove complete-event response
costs or the controlled-selection ceiling.

多个写入者或 worker 需要同时推进，或者持续多用户延迟有要求时应使用 PostgreSQL。SQLite
串行化写入，长写事务会拖延无关写入，WAL 不提供多个并发写入者。上传组装、哈希和对象校验已移至短发布事务之前；应使用有界
清单和隔离 home，不能从 S 冒烟推断生产并发。应根据实测表选择带内存、磁盘余量的工作点，
并重跑自己的实际负载再采用延迟目标；更换数据库不能消除完整事件响应成本或受控选择上限。

Recommended use is bounded by what was actually measured:

| Workload / 使用方式 | Recommendation / 建议 |
| --- | --- |
| Controlled version creation / 受控版本生成 | At most 10,000 selected files per operation; narrow larger datasets. / 单次最多选择1万文件，大数据集应缩小筛选。 |
| 100,000-file processing / 10万文件批处理 | Measured with eight workers; allocate memory for the parent and all workers, then rerun with real file sizes. / 已测8个worker，须同时预留主进程和全部worker内存，并按真实文件大小复测。 |
| 100,000-file interactive reads / 10万文件交互读取 | Prefer PostgreSQL and 50-entry pages; the complete 300ms read target is not established. / 优先PG和每页50条，完整300ms读取目标尚未达到。 |
| Team-tier annotators on one instance / 团队档同时标注人数 | PostgreSQL: 50 measured within the B8 targets on a quiet host; its latency rises steeply under CPU contention, so keep headroom. SQLite: 20 on a shared host, 50 on a dedicated one (both measured within target). / PG：空闲机器上 50 人达标，CPU 争抢时延迟陡增，需预留余量；SQLite 共享机器 20 人、独占机器 50 人（均实测达标）。 |
| 50 simultaneous users / 50人并发 | Do not promise a one-second p95 from this matrix; measure a lower client count before adopting an interactive SLA. / 本矩阵不支持承诺p95一秒，应先实测较低并发。 |
| 1,000,000-entry manifests / 百万清单 | Offline metadata persistence/comparison only; no measured interactive operating ceiling. / 仅作为离线元数据持久化与对比实验，没有已验证的交互上限。 |

No intermediate size or concurrency ceiling was measured by bisection. These are operating
recommendations, not extrapolated guarantees between the measured S and M points.

没有通过二分测试确定中间规模或并发上限。这些是使用建议，不是从 S、M 档外推的达标保证。

`make check` runs a real S dataset smoke plus a fourfold growth guard on the production ordered
manifest merge. Median measurement windows avoid absolute timing thresholds. The same validator
must reject a behavior-preserving O(n²) mutation; `--mutation` exits nonzero when injected.

`make check` 执行真实 S 数据集冒烟，并对生产版本清单合并做四倍规模退化检查。使用时间窗口
中位数和放大倍数，不以绝对延迟作门槛；同一判据必须拒绝保持结果正确的 O(n²) 变异，
`--mutation` 注入后应非零退出。
