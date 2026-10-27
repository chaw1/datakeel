# Annotation quality / 标注质量

Datakeel evaluates classification labels, 2D boxes and text spans entirely offline. Imports freeze a dataset version and a panel of named annotators. Every revision retains its metrics and review findings. The **Annotation quality** tab is available on dataset and version object pages; the latter shows only that immutable version.

Datakeel 可离线评估分类标签、二维目标框与文本片段。导入时绑定数据集版本和具名标注员，每次修订保留指标及疑似错标。数据集与版本对象页均有「标注质量」页签，版本页只显示该不可变版本的结果。

## Input / 输入

`AnnotationImportRequest` contains `version_id`, a unique retry `idempotency_key`, and `batch`. Every `sample_id` must be a file in that version. A sample/annotator pair may appear once. `labels`, `boxes` and `spans` may be supplied together or independently: `null` means missing, while `[]` means reviewed and empty. Reusing a retry key with changed inputs is rejected.

`AnnotationImportRequest` 含 `version_id`、用于重试去重的 `idempotency_key` 和 `batch`。`sample_id` 必须属于该版本清单，每个样本与标注员组合只能出现一次。`labels`、`boxes`、`spans` 可同时或分别提供：`null` 表示缺失，`[]` 表示已检查且为空。同一重试键不能换一组输入。

```json
{
  "version_id": "version-id",
  "idempotency_key": "harbor-panel-1",
  "name": "First panel",
  "batch": {
    "annotations": [
      {
        "sample_id": "file-id",
        "annotator_id": "reviewer-amber",
        "labels": ["clear"],
        "boxes": [{"category": "beacon", "x1": 20, "y1": 20, "x2": 40, "y2": 40}],
        "spans": [{"category": "beacon_name", "start": 7, "end": 12}],
        "image_width": 128,
        "image_height": 96,
        "text_length": 29
      }
    ],
    "exclusive_label_groups": [["clear", "restricted"]],
    "near_duplicates": [{"sample_id": "file-id", "other_sample_id": "other-file-id"}],
    "iou_threshold": 0.5,
    "label_mode": "auto"
  }
}
```

`label_mode` is `auto` (infer single-select behaviour), `single` or `multi`. `near_duplicates` lists sample pairs known to show the same content, for example from the existing image dHash evidence. Box coordinates use `xyxy` pixels. Spans are half-open character offsets `[start,end)` in the associated text. Invalid coordinates remain reviewable input; they generate findings instead of disappearing during import. Existing evidence sidecars remain supported; this version-scoped panel adds annotator identities needed for agreement.

`label_mode` 取 `auto`（从批次推断是否单选）、`single` 或 `multi`。`near_duplicates` 列出内容近似重复的样本对，例如来自现有图片 dHash 证据。框采用像素 `xyxy` 坐标，片段为对应文本的半开字符区间 `[start,end)`。非法坐标会保留并产生复核项，不会在导入时静默丢弃。原有证据 sidecar 继续可用；版本标注批次补充了计算一致性所需的标注员身份。

## Metrics / 指标定义

| Output / 输出 | Definition / 定义 |
|---|---|
| Cohen κ | Pairwise chance-corrected nominal agreement on samples both annotators reviewed. 多选标签按去重后的完整标签集作为一个名义类别；只计算双方都有分类标注的样本。 |
| Fleiss κ | Equal-size panels, with missing or unequal panels explicitly reported as unavailable. 等人数评审面板；不满足条件时返回明确原因。 |
| Krippendorff α | Nominal disagreement using available ratings, allowing missing values. 使用已有标注的名义分歧，允许缺失。 |
| Raw agreement / 原始一致率 | Reported alongside κ/α; class imbalance can make chance-corrected agreement diverge from raw agreement. 与校正后指标同时展示，避免类别分布不均时只看 κ。 |
| Confusion / 混淆矩阵 | For every annotator pair, a K×K matrix: `matrix[i][j]` counts samples the first annotator put in `categories[i]` and the second in `categories[j]` (a multi-label set is one category joined by `+`, an empty set is `(empty)`). Per-label one-vs-rest TP/FP/FN/TN counts are also returned. 每对标注员一张 K×K 矩阵，行是第一位、列是第二位；多选组合按一个类别计。另附每个标签的一对多 TP/FP/FN/TN。 |
| Box match rate / 框匹配率 | Descending-IoU greedy one-to-one matching, deterministic index tie breaks, at the configured threshold; `2 × matches / (left + right)`. 按 IoU 从高到低贪心一对一匹配，同分按索引决定。 |
| Box IoU and category / 框 IoU 与类别 | Mean IoU and category agreement among geometric matches. 几何匹配成功的框对内计算平均 IoU 与类别一致率。 |
| Span F1 / 片段 F1 | Same-category exact or positive-overlap maximum-cardinality matching; micro `2 × matches / (left + right)`. 同类精确或正重叠最大匹配，跨样本微平均。 |

Undefined estimates use `value: null` and a reason, never NaN or an invented perfect score. Missing reviews are excluded from the applicable pair, rather than interpreted as an empty label. The algorithms and their published numerical examples are tested in `tests/annotation_qa/`.

未定义的估计返回 `value: null` 与原因，不使用 NaN，也不虚构满分。缺失标注从适用的成对计算中排除，不视为空标签。算法与已发表数值算例见 `tests/annotation_qa/`。

## Sampling and approval / 抽检与签批

AQL lookup uses the checked-in [normal single sampling contract](../contracts/annotation_qa/normal-single.json): general inspection level II, normal inspection, single sampling, supported AQL columns `0.010` to `10` (percent defective units). ISO 2859-1 and GB/T 2828.1 Table 2-A use the same cells for these columns. Below each column's Ac=0 plan the table reads up arrow, then down arrow, then Ac=1; for example lot 281–500 (letter H) at AQL 0.65 follows the arrow to J: n=80, Ac=1, Re=2. When the plan's sample size reaches the lot size, the whole lot is inspected. The original letter, effective letter after table arrows, sample size, acceptance number and rejection number are retained. Unsupported columns fail explicitly. Fixed-ratio sampling instead requires a ratio and an acceptance number; it is labelled separately from AQL.

AQL 查表使用仓库中的[正常检验一次抽样合同](../contracts/annotation_qa/normal-single.json)：一般检验水平 II，支持 AQL `0.010` 至 `10`（不合格品百分数），与 ISO 2859-1、GB/T 2828.1 表 2-A 相应列一致。每列 Ac=0 方案下方依次是上箭头、下箭头、Ac=1，例如批量 281–500（字码 H）在 AQL 0.65 时按箭头取 J：n=80，Ac=1，Re=2。样本量达到批量时全检。保存原始字码、按表格箭头确定的实际字码、样本数、接收数与拒收数，不支持的列明确拒绝。固定比例方案另行指定比例及接收数，独立标识，不能冒充标准表方案。

Selection ranks distinct sample IDs by SHA-256 of seed and identity. The same batch and seed always select the same units regardless of input order. A plan freezes the batch digest and selected units. Review every selected unit and provide a reason for each defective unit. The `annotation_acceptance` controlled action requires approval before recording acceptance or rejection; its saved inspection preserves error details and action identity. Several errors on one sampled unit count as one defective unit.

抽样按种子与样本身份的 SHA-256 排序，相同批次与种子得到相同样本，不受输入顺序影响。方案冻结批次摘要和样本清单，必须逐项复核并为不合格项写明原因。`annotation_acceptance` 受控动作必须签批后才能保存接收或拒收结论，历史包含错误明细与动作身份。同一样本多个错误只计一个不合格样本。

## Suspicions and rework / 疑似错标与返工

Every rule uses only the annotations and batch statistics; no model is called. Each finding has a stable identity (sample, annotator, rule, item), a reason and evidence lines.

| Rule / 规则 | Signal / 信号 |
|---|---|
| `minority_label` | With at least three raters, a label set differs from a strict majority. 三人以上严格多数下的少数派标签。 |
| `near_duplicate_conflict` | Two samples in a near-duplicate pair have different strict-majority label sets; the majority holders on both sides are flagged. 近重复样本对的多数标签不同。 |
| `multilabel_conflict` | Labels from a declared exclusive group; more than one label with `label_mode=single`; more than one label when at most 1% of at least 20 labelled records have several (`auto`); or two labels that co-occur in at most 2% of the rarer label's records although independence predicts at least five co-occurrences. 声明互斥、声明单选、批次实为单选（≤1%多选）、或统计上几乎从不共现的两个标签同时出现。 |
| `bbox_category_minority`, `span_category_minority`, `span_boundary_minority` | Boxes (IoU ≥ batch threshold) and spans (positive overlap) are matched one-to-one per annotator pair and clustered; within a cluster supported by a strict majority of the sample's panel (≥3 annotators), a category or span offsets differ from the cluster's strict majority. 跨标注员匹配聚类后，类别或片段边界与多数不一致。 |
| `bbox_missing`, `span_missing` | A strict-majority cluster has no item from this panel member (`[]` counts as reviewed; `null` does not). 多数人标了、此人漏标。 |
| `bbox_extra`, `span_extra` | An item only its own annotator drew while at least two other panel members reviewed that modality. 只有此人标的框或片段。 |
| `duplicate_bbox`, `duplicate_span` | One annotator drew two boxes with IoU ≥ 0.9, or marked identical span offsets twice. 同一人重复框或重复片段。 |
| `bbox_size_outlier`, `bbox_aspect_outlier`, `span_length_outlier` | Within one category, log area (relative to the image when declared), log aspect ratio or log span length deviates from the median by at least 4x / 3x / 3x and either has modified z-score 0.6745·|x−median|/MAD above 3.5 (Iglewicz and Hoaglin 1993) or lies that factor beyond the cohort's 1st–99th percentile range. An item matched by another annotator needs a modified z above 5. Cohorts need ten items; a cohort where over 10% would be flagged is treated as multimodal and skipped. 按类别的对数面积、长宽比、片段长度稳健离群。 |
| `invalid_bbox`, `invalid_span` | Nonpositive size, negative origin, or beyond declared image size / text length. Invalid items are excluded from statistics and are not also reported as missing. 越界或非法坐标。 |
| `rare_category` | A label, box category or span category used exactly once among at least 50 such annotations, a likely typing error. 至少 50 个标注中只出现一次的类别，常见于拼写错误。 |

Findings request human review; a near duplicate or minority vote is not proof of an incorrect label. On generated three-annotator panels (three size distributions, two seeds each) every planted error type is found and at most 2% of clean samples are flagged; see `tests/annotation_qa/test_generated_panels.py`.

以上规则只用标注本身和批次统计，不调用模型；每条疑似含稳定身份、原因和证据。疑似只表示需要人工复核。生成数据测试见 `tests/annotation_qa/test_generated_panels.py`：埋入的各类错误全部被发现，干净数据被标记的样本不超过 2%。

Export rework lists as CSV or JSON. Import the repaired panel with `rework_of` pointing to the original batch in the same version. Comparison distinguishes corrected, introduced, remaining and unassessed findings. Removed reviews are unassessed, so dropping troublesome rows cannot count as a fix. It also counts changed, unchanged, added and removed sample/annotator records, and, when an approved inspection of the original batch marked units defective, how many of those units were changed. Summary counts feed quality scoring, analysis reports and the dataset-version view.

返工清单可导出 CSV/JSON。导入返工批次时，`rework_of` 指向同版本的原批次。对比分别统计已修正、新增、遗留和未重新评估的复核项；删掉标注不会被算成修正。另统计改动、未改、新增、删除的标注记录数，以及原批次抽检判为不合格的样本中有多少在返工中被改动。摘要进入质量评分、分析报告与数据集版本页。

## Offline demonstration / 离线演示

The normal `uv run datakeel demo` includes **Aster harbor · annotation quality demo**: 24 fictional harbor images with generated notes, three reviewers, classification/boxes/spans and planted errors that produce ten finding types (19 findings). An AQL 6.5 plan (lot 24, letter C, arrow to D: n=8, Ac=1, Re=2) samples two flagged units, which the generated reviewer confirms, so the approved inspection rejects the batch. Because file identities are generated at import, the demo uses the first seed from 26 whose sample shows exactly two flagged units. The rework revision corrects all 19 findings, changes both rejected units and deliberately introduces one new invalid span. No model is initialized.

普通演示包含 **Aster harbor · annotation quality demo**：24 张虚构港口图及生成文字，三名标注员，分类、框和片段，埋入的错误产生十类共 19 条疑似。按 AQL 6.5 抽检（批量 24，字码 C 按箭头取 D：n=8，Ac=1，Re=2），抽中两件有疑似的样本并确认不合格，签批后判定拒收。文件身份在导入时生成，演示取从 26 起第一个恰好抽中两件疑似样本的种子。返工修正全部 19 条疑似、改动了两件不合格样本，并故意引入一条新的片段错误，全程不初始化模型。

Generate portable panels only:

仅生成文件：

```bash
uv run python scripts/generate_annotation_qa_demo.py --output /tmp/annotation-qa-samples
```

Import into an explicitly selected local SQLite database, then serve that workspace:

导入指定本地 SQLite 数据库，再启动同一工作区：

```bash
export DATAKEEL_HOME=$(mktemp -d)
uv run python scripts/generate_annotation_qa_demo.py \
  --output "$DATAKEEL_HOME/samples" --database "$DATAKEEL_HOME/datakeel.db"
uv run datakeel api --host 127.0.0.1 --port 8773
```

The import refuses a configured S3 backend to keep this generated demonstration offline. For an isolated shell, unset inherited `DATAKEEL_DATABASE_URL`, `DATAKEEL_S3_BUCKET` and `DATAKEEL_S3_ENDPOINT` before running. Open the generated dataset's **Annotation quality** tab. In an offline `fake-demo` conversation bound to this dataset, ask `这批标注一致性怎么样?` or `How is annotation agreement?`; the discovered read-only `annotation_quality` tool returns the saved history and never prepares or executes acceptance.

导入命令检测到 S3 配置会拒绝运行，保证本演示只使用本地存储。隔离终端可先清除继承的上述数据库及 S3 配置。打开生成数据集的「标注质量」页签；在绑定此数据集的离线 `fake-demo` 会话里询问「这批标注一致性怎么样?」，Agent 通过按需发现的只读 `annotation_quality` 工具读取已保存历史，不准备或执行验收动作。
