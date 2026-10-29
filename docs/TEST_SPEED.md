# Test execution speed / 测试执行提速

Parallel execution changes scheduling and fixture setup, never the selected tests or the
quality thresholds. `make check` still runs the complete gate; `scripts/ci-check.sh` also
runs the README checks and every declared mutation. The existing default
`-m 'not integration'` is unchanged. Overall coverage remains at least 85%, and the
domain coverage checks in `scripts/check_coverage.py` still run after the merged report.

并行只改变调度与夹具准备，不改变用例选择和质量门槛。`make check` 仍执行完整门禁；
`scripts/ci-check.sh` 另执行 README 检查和全部变异锚。原有默认
`-m 'not integration'` 不变，总覆盖率仍须达到 85%，合并报告后仍执行领域覆盖率检查。

## Scheduling options / 调度方式比较

| Option / 方式 | Behavior / 行为 | Fit here / 本仓取舍 |
| --- | --- | --- |
| xdist `load` | Dispatch pending tests to available workers. / 按空闲情况派发用例。 | Fine granularity; expensive fixtures may repeat. / 粒度细，昂贵夹具可能重复。 |
| xdist `loadfile` | Keep each file on one worker. / 同一文件留在同一 worker。 | Reuses file fixtures; slow files limit balance. / 便于复用夹具，慢文件可能拖尾。 |
| xdist `loadscope` | Group functions by module and methods by class. / 函数按模块、方法按类分组。 | Useful for costly module/class fixtures. / 适合昂贵模块或类夹具。 |
| xdist `loadgroup` | Keep each `xdist_group` together; dispatch unmarked tests as `load`. / 相同 `xdist_group` 留在同一 worker，未标记用例按 `load` 派发。 | Shares a Docker fixture but allows other workers to compete for resources. / 可复用 Docker 夹具，其它 worker 仍会争用资源。 |
| Repository security scheduler / 本仓安全调度器 | Run the security group alone, then execute ordinary cases concurrently. / 安全组先独占执行，再并行执行普通用例。 | Protects container startup and cleanup; adds a serial phase. / 保护容器启动与清理，代价是增加独占阶段。 |
| xdist `worksteal` | Redistribute queued tests from busy workers. / 空闲 worker 从繁忙队列取任务。 | Handles variable durations; no file affinity guarantee. / 应对耗时差异，不保证文件亲和。 |
| Separate pytest shards / 多个 pytest 分片 | Manually partition node IDs and merge reports. / 自行划分节点并合并报告。 | Adds collection, completeness and reporting logic. / 需额外维护收集完整性与报告。 |
| Python process pool / Python 进程池 | Execute picklable work in separate interpreters. / 独立解释器执行可序列化任务。 | Suitable for independent jobs; does not supply pytest scheduling or reporting. / 适合独立任务，不能直接替代 pytest 调度和报告。 |
| Python thread pool / Python 线程池 | Share an interpreter while overlapping work. / 共用解释器并发执行。 | Suitable for supervising subprocesses, unsafe for simultaneous in-process pytest sessions. / 可管理子进程，不宜在同一进程并跑 pytest 会话。 |

The xdist scheduler semantics and fixture behavior above come from its
[distribution guide](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)
and [fixture guide](https://pytest-xdist.readthedocs.io/en/stable/how-to.html#making-session-scoped-fixtures-execute-only-once).
Process/thread tradeoffs follow the
[Python 3.12 executor documentation](https://docs.python.org/3.12/library/concurrent.futures.html).
The fit assessment is based on this repository's fixtures and runners.

上表调度及夹具语义以官方指南为据，进程池与线程池行为以 Python 3.12 官方文档为据；
适用性一列是结合本仓夹具和执行器的判断。xdist 的 session 夹具每个 worker 各执行一次，
不是整个分布式运行只执行一次。

## Isolation and coverage / 隔离与覆盖率

- The session fixture in `tests/conftest.py` creates one migrated empty source per worker,
  using `tests/db_templates.py`. Tests receive copies and never write to that source.
  `DATAKEEL_HOME` remains inside each test's temporary directory.
  / 根 session 夹具通过 `tests/db_templates.py` 为每个 worker 创建一个迁移完成的空模板；
  用例获得副本，不写模板，`DATAKEEL_HOME` 仍位于各用例临时目录。
- SQLite uses `sqlite3.Connection.backup()` to make a full database copy for each `db`
  fixture. Teardown disposes the engine and removes that copy plus its `-wal` and `-shm`
  sidecars; session cleanup removes the worker's source file.
  / SQLite 的每个 `db` 夹具通过 `sqlite3.Connection.backup()` 获得完整数据库副本；
  清理时释放 engine，删除该副本及其 `-wal`、`-shm` 文件，会话结束后删除 worker 模板。
- PostgreSQL creates a private `datakeel_template_<UUID>` database from `template0`,
  migrates a `test_<UUID>` schema there, and clones the whole database into a fresh
  `datakeel_test_<UUID>` database per test. The same schema name may exist in different
  databases; their facts and connections remain separate. Database constraints, functions
  and triggers are retained with the schema objects, rather than rebuilt from table-only
  metadata. Connections use the copied schema's search path.
  / PostgreSQL 从 `template0` 创建私有 `datakeel_template_<UUID>` 数据库，在其中迁移
  `test_<UUID>` schema，再为每个用例克隆为新的 `datakeel_test_<UUID>` 完整数据库。
  不同数据库中可以有相同 schema 名，其事实和连接仍独立；复制保留约束、函数和触发器等
  schema 对象，不以仅含表结构的 metadata 重建，连接仍设置对应 search path。
- PostgreSQL fixtures reject hosts other than `localhost` or `127.0.0.1`. The local test
  role needs `CREATEDB` and permission to clone the template; the fixture owns the
  templates it creates. Cleanup drops only UUID databases recorded as created by that
  template owner, after disposing their engines. It does not use `DROP DATABASE ... FORCE`
  or terminate other connections.
  / PostgreSQL 夹具继续拒绝 `localhost`、`127.0.0.1` 以外的主机。本地测试角色须有
  `CREATEDB` 及克隆模板的权限，夹具拥有自己创建的模板。清理先释放 engine，只删除当前
  owner 记录为自己创建的 UUID 数据库，不使用 `DROP DATABASE ... FORCE` 或终止其它连接。
- `unmigrated_db` retains the original migration-test path: each test gets an empty SQLite
  file or its own PostgreSQL schema in the supplied database, then executes the migrations
  under test. Teardown drops only that schema and disposes its engine.
  / `unmigrated_db` 保留原迁移测试路径：每用例创建空 SQLite 文件，或在指定 PostgreSQL
  数据库内创建独立 schema，再执行待测迁移；清理仅删除该 schema 并释放 engine。
- Most child fixtures generate data in `tmp_path` and retain function scope.
  Environment and module monkeypatches stay within the worker process and are undone by
  pytest. These properties must be preserved when reducing fixture setup cost.
  / 大部分子夹具在 `tmp_path` 内按用例生成数据；环境和模块 monkeypatch 留在 worker
  进程内，由 pytest 撤销。缩短夹具准备耗时时仍须保留这些性质。
- The real sandbox fixture owns a unique Docker image tag and its build state directory.
  It removes only its exact tag. Session fixture duplication must be considered when
  choosing worker count and scheduler; a scheduler does not make shared paths safe.
  / 真实沙箱夹具拥有唯一镜像 tag 和独立构建状态目录，只删除自己创建的精确 tag。
  选择并行数与调度方式时须考虑 session 夹具重复，调度方式本身不能隔离共享路径。
- pytest-cov supports xdist and combines worker coverage into one report. Keep the existing
  terminal, XML and JSON reports and apply all thresholds to the combined result.
  This differs from coverage in ordinary child processes: pytest-cov 7 removed its own
  subprocess instrumentation; enabling that separately would require coverage's subprocess
  patch and is outside the scheduling change.
  / pytest-cov 原生支持 xdist 并合并 worker 覆盖率。保留终端、XML、JSON 报告，门槛作用于
  合并结果。普通子进程覆盖率是另一件事：pytest-cov 7 已移除自己的子进程采集；如另行
  启用，需要 coverage 的 subprocess patch，不应与本次调度改动混淆。

Sources: [pytest-cov xdist support](https://pytest-cov.readthedocs.io/en/stable/xdist.html),
[pytest-cov subprocess migration](https://pytest-cov.readthedocs.io/en/stable/subprocess-support.html).
The fixture descriptions above are derived from repository code.

Repeated PostgreSQL migrations retain installed training triggers, checking both the trigger
name and the schema-resolved table OID before creating a missing trigger. Function bodies
still use `CREATE OR REPLACE`. This follows the existing release/lineage constraint pattern
and avoids trigger DDL blocking an active version writer. Trigger event-definition changes
need an explicit migration; ordinary startup does not repair manually altered triggers.

PostgreSQL 重复迁移会按触发器名称和当前 schema 的表 OID 判断是否已安装训练约束，
只创建缺失触发器，函数体仍通过 `CREATE OR REPLACE` 更新。该方式沿用发布和血缘约束的
既有模式，避免触发器 DDL 阻塞正在写版本的事务。触发事件定义变更需要显式迁移，
普通启动不负责修复被手工改动的触发器。
Copy and privilege semantics are documented by
[SQLite's backup API](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup)
and [PostgreSQL 17 CREATE DATABASE](https://www.postgresql.org/docs/17/sql-createdatabase.html).

## Commands and default / 入口与默认值

`make check-python` uses `uv run python -m scripts.run_pytest` for the full pytest step.
The wrapper selects `--dist loadgroup` and explicitly loads `scripts.pytest_groups` with
`-p` so the plugin also runs in workers. The plugin marks only
`tests/operators/custom_sandbox/test_security.py` with the security `xdist_group` and
installs the scheduler in `scripts.pytest_scheduler`.

`make check-python` 的完整 pytest 步骤通过 `uv run python -m scripts.run_pytest` 执行。
默认选择 `--dist loadgroup`，通过 `-p` 显式加载 `scripts.pytest_groups`，确保 worker
也执行插件。插件只给 `tests/operators/custom_sandbox/test_security.py` 添加安全组
`xdist_group`，并安装 `scripts.pytest_scheduler` 中的调度器。

The selected security tests run first on one worker while the other workers stay idle.
Only after that phase completes do ordinary cases execute concurrently. Group affinity
alone would avoid duplicate image builds but would still allow CPU and I/O contention
during container startup and cleanup. The exclusive phase covers both. A security failure
still fails the gate; the scheduler does not reinterpret a timeout or missing cleanup as
success. A worker crash aborts the run rather than treating unfinished cases as completed.
All phases belong to one pytest session with one merged coverage report.

被选中的安全用例先在一个 worker 上执行，其它 worker 保持空闲；独占阶段结束后，才并行
执行普通用例。仅设置组亲和只能避免重复构建镜像，仍会在容器启动和清理时争用 CPU 与
I/O；独占阶段同时保护这些操作。安全测试失败仍使门禁失败，调度器不会把超时或缺少清理
视为成功；worker 崩溃会终止本次运行，不把未完成用例算作已完成。所有阶段属于同一个
pytest 会话，最终只合并一份覆盖率报告。

`scripts.pytest_priorities` holds a static list of complete node IDs for expensive cases.
After the security phase, these cases are dispatched early to reduce the final long tail.
Unlisted tests keep their relative order; no test is removed, duplicated or selected from
a timing cache. The priority list contains no measured timings or machine-specific data.
Other tests remain ungrouped and can run separately even when they share a file.

`scripts.pytest_priorities` 保存昂贵用例的完整 node ID 静态列表。安全阶段后优先派发这些
用例，减少末尾长尾；未列出的用例保持相对顺序。不会删除、重复用例，也不根据计时缓存
筛选用例。优先级列表不包含实测耗时或机器专属数据；其它用例不分组，即使在同一文件中
也可分别执行。

`loadfile` was considered for fixture reuse, but it also serializes every case in a heavy
CLI evaluation file. Selective grouping and explicit priorities avoid that file-wide
restriction. Scheduling marks and priorities do not change `-m 'not integration'`, test
membership, assertions or coverage thresholds.

`loadfile` 有利于复用夹具，但也会让重型 CLI evaluation 文件内的所有用例串行执行。
精确分组与显式优先级避免整文件绑定。调度 marker 和优先级不改变
`-m 'not integration'`、用例集合、断言或覆盖率门槛。

The worker policy in `scripts.test_workers.test_worker_count()` is
`max(1, min(16, os.cpu_count() or 1))`. The cap bounds memory, process, database and temporary
disk demand. Override it with a positive integer in `DATAKEEL_TEST_WORKERS`.
`DATAKEEL_TEST_WORKERS=1` executes serially. The same policy bounds mutation concurrency.
CI uses the same wrapper and sets the count explicitly for its four-core runner.

`scripts.test_workers.test_worker_count()` 的默认公式为
`max(1, min(16, os.cpu_count() or 1))`，上限限制内存、进程、数据库连接和临时磁盘需求。
可用环境变量 `DATAKEEL_TEST_WORKERS` 设为正整数覆盖；设为 `1` 时串行执行。
变异并发复用相同策略；CI 使用同一入口，并为四核 runner 显式设置并行数。

```bash
make check-python
DATAKEEL_TEST_WORKERS=1 make check-python
DATAKEEL_TEST_WORKERS=4 scripts/ci-check.sh
uv run pytest --collect-only -q
```

Direct pytest commands retain their normal semantics; collection does not need worker
startup. Neither a smaller worker count nor serial execution changes test selection.

直接调用 pytest 保留原有语义，收集用例无需启动 worker；减少 worker 或串行执行不改变用例集合。

## Mutation execution / 变异执行

Each mutation keeps its own `TemporaryDirectory`, source copy, home, SQLite database and
subprocess environment. A successful unmodified baseline is required before mutated jobs
start. A pytest mutant must still produce exactly its declared test's measured call
assertion; setup errors, skips and crashes never count as a kill. The special explanation
probe remains confined to its mutant's source copy. Concurrency must be bounded rather
than creating one worker per mutation, and results must retain catalogue order.

每个变异继续拥有独立临时目录、源码副本、home、SQLite 数据库和子进程环境；原始基线必须
先全部通过，才启动变异。pytest 变异仍须有且仅有目标用例的实际调用断言失败，准备阶段
错误、跳过和崩溃不能算 KILLED。特殊解释探针仍仅修改对应变异副本。并发必须有上限，
不能每个变异都创建一个 worker；输出顺序应与变异目录一致。

The mutation supervisor uses `ThreadPoolExecutor`: each task already starts a separate
interpreter, so another process pool would add an unnecessary interpreter and serialization
layer. Every pytest subprocess disables nested xdist with `-n0`. Each baseline job also
uses its own source copy, and all baseline jobs must pass before the mutation pool starts.
Executor `map` preserves catalogue order when collecting results.

变异管理器使用 `ThreadPoolExecutor`：每项任务本来就启动独立解释器，再套进程池会增加解释器
和序列化开销。pytest 子进程通过 `-n0` 禁用嵌套 xdist；每项基线也使用独立源码副本，所有
基线通过后才启动变异池。通过 executor 的 `map` 按目录顺序收集结果。

## Measurement protocol / 测量方法

Measure SQLite and PostgreSQL separately, with at most one complete gate running at a
time. Record commit, worker count, test count, wall time, exit status and `uptime` before
and after every measurement. Run the serial baseline and parallel comparison consecutively
under comparable machine load. Preserve the slowest 50 tests with `--durations=50` and
record step times for the complete gate. A failed or interrupted run is not a completed
performance result. Sandbox restrictions are failures to report, never a reason to add
skip, xfail or deselection.

Treat the original baseline snapshot as read-only: optimized fixtures and scheduling
belong only in the comparison checkout. Preserve baseline logs even if the run cannot
finish within the task time limit.

SQLite 与 PostgreSQL 分别计时，同一时间最多执行一条完整门禁。每次记录提交、worker 数、
用例数、耗时、退出码及运行前后的 `uptime`。串行基线和并行对照应在相近负载下连续执行；
用 `--durations=50` 保留最慢 50 个用例，并记录完整门禁各步耗时。失败或中断不能算完成的
性能结果；沙箱限制只如实报告，不能据此新增 skip、xfail 或排除用例。

原始基线快照只读使用，优化后的夹具和调度只写入对照工作区。即使基线无法在任务时限内
完成，也保留原始日志。

## Changed-test selection: deferred / 改动影响选择：暂缓

No `check-changed` shortcut is implemented in this change. Full test and mutation execution
remain the required gate. The following comparison records options for a separately
validated future shortcut.

本次不实现 `check-changed`，完整测试和变异仍是必需门禁。下表保留后续实现快速门禁时的
选型依据；任何方案都须独立验证可信度。

| Method / 方法 | Strength / 优点 | Conservative fallback needed / 须保守兜底 |
| --- | --- | --- |
| pytest-testmon | Records executed dependencies and detects changed code using its own database. / 记录实际执行依赖，以自身数据库判断代码变化。 | Requires a complete initial run and valid state for each backend/environment; non-Python resources need extra rules. / 每个后端和环境均需完整初始记录及有效状态，非 Python 资源需补充规则。 |
| Static import graph / 静态 import 图 | No historical coverage database; reverse transitive imports give an explainable file set. / 无需历史覆盖库，可解释地反向遍历传递 import。 | Dynamic imports, fixtures, configuration and data dependencies need explicit edges or full execution. / 动态导入、夹具、配置和数据依赖须显式补边，否则全跑。 |
| Coverage test contexts / 覆盖率用例上下文 | Maps measured lines to test IDs, using the existing coverage tooling. / 复用现有覆盖工具，把执行行映射到用例节点。 | An unexecuted/new path has no historical edge; stale, incomplete or mismatched data must trigger full execution. / 新路径或未执行路径缺乏历史边，数据过期、不完整或不匹配时须全跑。 |

testmon's initial-run requirement and dependency model are documented by
[its maintainers](https://www.testmon.org/).
Python exposes static `Import` and `ImportFrom` nodes through
[the AST API](https://docs.python.org/3.12/library/ast.html).
Coverage documents [measurement contexts](https://coverage.readthedocs.io/en/latest/contexts.html),
and pytest-cov supports full parameterized test IDs with
[`--cov-context=test`](https://pytest-cov.readthedocs.io/en/stable/readme.html).
The fallback rules are repository design requirements, not guarantees from these tools.

testmon 的初始全跑要求及依赖模型、Python AST 的 import 节点、coverage 的上下文数据能力
均见上述官方来源；保守兜底规则是本仓必须另行实现的约束，并非工具自动保证。

A future implementation must always run repository-wide static checks, select mutations
whose target source files changed, and rerun everything for uncertain impact. Validation
must replay three historical fixes with their source changes removed and demonstrate that
the shortcut reports failure in each case. Full coverage gates remain separate because
coverage from a selected subset cannot establish whole-suite coverage.

后续实现须始终运行全仓静态检查，执行目标源码文件被改动的变异锚，影响无法确定时全跑。
验收须选取三个历史修复提交，分别撤掉源码修复并证明快速门禁报红。子集测试覆盖率不能
证明完整覆盖率，因此仍须保留独立的全量覆盖率门禁。
