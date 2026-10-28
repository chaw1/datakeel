# Table and time-series profiling / 表格与时序剖析

Datakeel inspects local CSV/TSV files using the standard library and numeric statistics. Parquet is optional: install `pyarrow` yourself to read it. No model, telemetry or additional core runtime dependency is required. Spreadsheet workbook formats are retained unchanged by the default pipeline.

Datakeel 使用标准库读取本地 CSV/TSV，并以数值统计检查表格与传感器信号。Parquet 需要用户自行安装 `pyarrow`，缺少时返回明确提示。无需模型、遥测或新增核心依赖。默认流水线保留未支持的工作簿文件。

## One-command example / 一条命令演示

```sh
DATAKEEL_HOME=.datakeel-sensors uv run datakeel timeseries-demo
```

The command generates one week of five-minute observations from three fictional smart-kitchen devices, imports them, prepares and executes the existing `run_pipeline` action, drains the local worker, then uses `import_catalog` to publish column profiles. It prints dataset/task/action identities and writes `report.md` and `quality.json` under the configured data directory. `--output reports/sensors` chooses the generated source and report directory. Run `uv run datakeel api --port 8814` with the same `DATAKEEL_HOME` to inspect the dataset report and catalog table objects.

命令合成三台虚构智能厨房设备一周、每五分钟一条的观测，导入后经既有 `run_pipeline` 受控动作运行本地 worker，再经 `import_catalog` 受控动作发布目录剖析。输出包含数据集、任务、动作 ID，数据目录下生成 `report.md` 和 `quality.json`；`--output reports/sensors` 可指定源文件及报告目录。使用相同 `DATAKEEL_HOME` 运行 `uv run datakeel api --port 8814`，即可打开数据集报告和目录表对象页。

The generated faults include mixed timezone representations, descending timestamps, two sampling gaps, a stuck temperature sensor, isolated spikes exceeding the physical range, mixed gas-flow units, and fictional phone contacts. A separate clean week is tested for at most two unplanted detections. Sources contain no real device or brand data.

埋入的问题包括时区表示混用、时间乱序、两段断档、温度卡值、超过物理量程的尖峰、燃气流量单位混用及虚构联系电话。测试另生成完整正常的一周数据，限制非埋入问题误报不超过两处。样例不含真实设备或品牌数据。

## Operators / 算子

All seven operators expose frozen `Params` schemas and reject unknown fields. Their manifest entries are in `contracts/operators.json`, and their file modality is `table`. Use a route node's `table` slot before a table-specific operator in a DAG. The default pipeline automatically profiles supported table files. For sensors, compose the explicit inspection chain with `datakeel.pipeline.tabular.timeseries_pipeline` or submit a custom DAG through the existing action/API.

七个算子均有冻结的 `Params` 模型，拒绝未知字段；合同位于 `contracts/operators.json`，文件模态为 `table`。DAG 中应先用路由节点的 `table` 槽位连接表格算子。默认流水线自动剖析支持的表格文件；传感器数据可使用 `datakeel.pipeline.tabular.timeseries_pipeline` 组合完整检查链，或通过既有动作/API 提交自定义 DAG。

| Operator / 算子 | Parameters and behavior / 参数及行为 |
| --- | --- |
| `table.profile` | Per-column type, null/distinct ratios, bounded distribution, candidate primary/foreign keys and suspected PII. / 逐列类型、空值与唯一率、分布摘要、候选主外键及疑似个人信息。 |
| `timeseries.timestamp_normalize` | `time_column`, optional `device_column`, `naive_timezone`, `numeric_unit=auto/s/ms`; ISO/epoch → UTC milliseconds. / 指定时间列、设备列、无时区时间的假设及数值单位，统一成 UTC 毫秒。 |
| `timeseries.order_dedup` | Sort per device; `keep=first/last` at duplicate timestamps. / 按设备排序，指定重复时间点保留策略。 |
| `timeseries.gaps` | `expected_interval_ms` or positive-delta median per device, `tolerance=1.5`; report bounded intervals and missing-sample duration. / 显式频率或按设备正时间差中位数，报告断档区间与缺失采样时长。 |
| `timeseries.resample` | `interval_ms`, `aggregation=mean/sum/min/max/first/last`, `value_columns`; UTC-aligned buckets with observations only. / 按 UTC 对齐分桶聚合，只输出有观测的桶。 |
| `timeseries.anomaly` | `value_columns`, `window=11`, `noise_floor=true`, `robust_z_threshold=6`, `stuck_min_points=5`, optional absolute `jump_threshold`, declared `ranges`. / 居中稳健 z 分数、完全相同值连续段、显式跳变量阈值及物理量程。 |
| `timeseries.unit_check` | `declarations=[{column,unit,minimum,maximum}]`; verify explicit suffixes and ranges. / 按列声明单位及量程，核对显式后缀与边界。 |

Timestamp normalization records observed formats, timezones and the inference basis. Auto epoch units use an absolute-magnitude threshold of 100,000,000,000; use `numeric_unit` for historical or otherwise ambiguous epochs. Naive values use only the declared timezone. Ambiguous and nonexistent daylight-saving local times are reported, not silently resolved. Other time-series operators expect normalized epoch milliseconds or explicit ISO timestamps.

时间归一化记录原格式、时区和推断依据；自动 epoch 单位以绝对值 100,000,000,000 为分界，历史或有歧义的 epoch 应显式设置 `numeric_unit`。无时区值仅按声明的时区解释，夏令时重复或不存在的本地时间会报告问题，不静默猜测。其他时序算子接收归一化后的 epoch 毫秒或显式 ISO 时间。

Statistical findings retain rule, threshold, window, device, original source rows, UTC interval and repair advice. Robust z uses a centered median/MAD window. Already identified exact stuck runs are excluded from its reference baseline; fewer than three remaining reference points produces no robust-z finding. By default the scale is at least the centered first-difference MAD divided by √2, estimated per contiguous device signal. Set `noise_floor=false` for local MAD without this noise bound. A zero scale falls back to the reference signal's MAD, then a 1% baseline floor. Exact-value runs are candidates for sensor sticking, not proof of a hardware fault. Set signal columns explicitly for categorical numeric controls. Resample after inspection to preserve spike evidence. Units are never guessed from bimodality and are never converted implicitly; bare numbers are interpreted in their declared unit.

每个统计问题保留规则、阈值、窗口、设备、原始行号、UTC 区间和修复建议。稳健 z 使用居中中位数/MAD，参考基线排除已识别的完全相同值连续段，剩余参考点少于三条时不下稳健 z 结论。默认尺度下界为每设备连续信号的一阶差分去中位数后 MAD/√2；`noise_floor=false` 可关闭该下界。尺度仍为零时退回参考信号 MAD，再退回基线绝对值的 1%。完全相同的连续值仅提示可能卡值，不能证明硬件故障。数值型档位等类别信号应显式选择检查列。先检查后重采样可保留尖峰证据。单位不由双峰分布猜测，也不隐式换算；裸数值按声明单位解释。

## Persistence and quality / 持久化与质量

Profiles and time-series summaries are preserved in immutable file-version metadata; source row numbers survive normalization and ordering. Quality scoring reads this recorded evidence without accessing sources. Completeness measures null cells and expected missing samples; consistency covers ordering, timezone representations, mixed types and unit conflicts; uniqueness covers duplicate device/timestamp keys; distribution covers signal anomalies. The existing annotation policy and five dimension weights remain in force. Detailed reasons identify columns and intervals, and the report adds a table/time-series chapter with per-column problems, anomaly counts, gap duration and repair suggestions.

表格与时序摘要保留在不可变文件版本元数据中，归一化与排序后仍可追溯原始行号。质量评分仅读取已记录证据：完整性计入缺失单元格和预期缺失采样，一致性计入乱序、时区表示、混合类型和单位冲突，唯一性计入设备/时间重复键，分布维度计入信号异常。既有标注策略及五维权重保持生效。详细扣分原因定位列和区间；报告新增逐列问题、异常区间数、断档时长和修复建议章节。

To publish file profiles into the catalog, prepare `import_catalog` with `request.files`, `source_id` and `name`, then execute the frozen plan using the existing approval policy. Profiles are computed during preparation; later source edits require a new plan. Published profiles and candidate keys are review evidence, never enforced constraints or accepted facts. PII distributions redact whole suspected columns. Catalog table/column object pages display profiles without exposing suspected contact values. Unsupported file-source SQL/schema options are rejected explicitly.

发布文件剖析到目录时，以 `request.files`、`source_id`、`name` 准备 `import_catalog` 动作，再按既有审批策略执行冻结计划。准备阶段计算剖析，源文件后续变化需要重新准备。剖析和候选键均为复核线索，不是强制约束或已确认事实。疑似个人信息列的分布整列隐藏原值；目录表/列对象页结构化展示剖析。文件源不支持的 SQL/schema 选项会明确拒绝。

## Ask published profiles / 查询已发布剖析

After the sensor command completes, ask `哪台设备的温度数据断档最多` or `Which device has the most gaps?` through the existing Ask data page, HTTP question endpoint, the `ask_data` tool or CLI:

```sh
DATAKEEL_HOME=.datakeel-sensors uv run datakeel ask '哪台设备的温度数据断档最多'
```

Only published version metadata is used. Chinese “断档最多” defaults to total missing-sample duration; “断档次数最多” and English “most gaps” rank interval counts. Both measurements are shown. A temperature column identifies the containing table: its sampling-axis gap does not prove temperature-only missingness. Multiple matching datasets require selection; missing, stale or incomplete provenance never produces a numeric ranking. Evidence links pin both the inspected published version and the original file/version containing the reported source row numbers. Other profile question forms retain the existing refusal behavior.

传感器命令完成后，可在既有问数页、HTTP `ask_data` 接口或 CLI 提问。仅读取已发布版本元数据。中文“断档最多”默认按缺失采样总时长，“断档次数最多”和英文“most gaps”按区间数排名，答案同时展示两者。温度列仅定位其所在表；表的采样时间轴断档不能证明温度独有缺值。多个数据集需要先选择；缺少、失效或不完整的来源不能给出数值排名。证据链接同时固定被检查的发布版本和原始行号对应的原文件版本。其他剖析问法沿用既有拒答行为。
