# Image and point-cloud quality / 图片与点云质量

Datakeel measures image usability and point-cloud geometry with local Pillow and NumPy operators. No model, network service or additional runtime package is required. Generated measurements feed the existing five quality dimensions, sample selection, reports and append-only lineage.

Datakeel 使用本地 Pillow 和 NumPy 算子检查图片可用性与点云几何质量，无需模型、网络服务或额外运行时依赖。测量结果进入既有五维评分、样本筛选、报告及追加式血缘。

## One-command demonstration / 一条命令演示

From the repository root, choose a new or empty local output directory:

在仓库根目录执行，输出目录须为新目录或空目录：

```sh
uv run python scripts/demo_media.py --output /tmp/datakeel-media-demo
```

The command creates five indoor scans: a room in ordinary coordinate units, a millimeter-scaled copy, a scan with scattered outliers, a scan with NaN/Inf coordinates and a sparsely sampled room. Eight generated PNGs cover a clear image, two blur strengths, overexposure, underexposure, noise, low resolution and a solid color.

脚本生成五份室内扫描：普通坐标单位的房间、放大到毫米尺度的副本、含离群点的扫描、含 NaN/Inf 坐标的扫描以及稀疏采样的房间；另生成八张 PNG，覆盖清晰、两档模糊、过曝、过暗、噪声、低分辨率和纯色。

It imports the samples into a dedicated SQLite database, submits `media_pipeline()`, drains the local worker, then reads the actual quality, report, immutable versions and lineage. The CLI starts its worker process with only an explicit local home and SQLite URL in its environment. It does not inherit model credentials, report endpoints, object-storage configuration or other database connections. The default pipeline measures originals without cleaning away the defects.

脚本将样本导入独立 SQLite，提交 `media_pipeline()` 并排空本地 worker，然后回读真实评分、报告、不可变版本与血缘。CLI 以仅包含明确本地目录和 SQLite 地址的干净环境启动处理子进程，不继承模型凭证、报告端点、对象存储配置或其他数据库连接。默认流水线只测量原始数据，保留问题供报告核验。

The output directory contains / 输出目录包含：

| File / 文件                | Contents / 内容                                                                                          |
| -------------------------- | -------------------------------------------------------------------------------------------------------- |
| `samples/`                 | Generated PLY, PCD and PNG sources / 生成的源文件                                                        |
| `state/`                   | Dedicated SQLite, local objects and worker outputs / 独立数据库、本地对象及处理产物                      |
| `summary.json`             | Task state, counts, score, issue codes overall and per file / 任务状态、数量、分数、总体及逐文件问题代码 |
| `quality.json`             | Five measured dimensions with reasons / 五维评分及扣分原因                                               |
| `report.md`, `report.json` | Rule-only report with image and point-cloud sections / 含图片与点云专节的规则报告                        |
| `versions.json`            | Original and processed immutable manifests / 原始与处理后的不可变清单                                    |
| `lineage.json`             | Source → operator → artifact events / 来源到算子再到产物的事件                                           |

## Image measurements / 图片测量

`image.quality` emits five scores, per-check failures and explanations, plus an overall score. It measures Laplacian sharpness at a normalized analysis size (larger images are reduced to `analysis_size`; smaller images are measured natively rather than enlarged), native-pixel noise, brightness and clipped pixel fractions, the shortest image side, and color variation. Decode corrects EXIF orientation before measurement. Each check has configurable parameters; the overall score reflects the weakest usability check so a severe defect remains eligible for the existing approved low-quality cleanup workflow.

`image.quality` 输出模糊、曝光、噪声、分辨率、纯色五项得分、各项是否失败及原因，并给出总分。信号分别来自统一分析尺寸下的拉普拉斯清晰度（大图缩小到 `analysis_size`，小图按原尺寸测量、不放大）、原生像素噪声、亮度与截断像素占比、图片最短边和颜色变化。测量前会校正 EXIF 方向。各项阈值可配置；总分取可用性最弱项，使单项严重缺陷仍能进入既有低质样本筛选及签批清理流程。

Complete the measurement pipeline before starting the bundled `low-quality-cleanup` workflow in the same dataset environment. Supply `dataset_id` and, optionally, `quality_max` (default 60, inclusive). Matching files are quarantined first; deletion waits for human approval. Return to the workflow and explicitly resume it to finish the quality recheck. Rejected or unsigned deletion plans do not delete files. See [workflow instructions](WORKFLOWS.md) for the Web, CLI and API steps.

先完成测量流水线，再在同一数据集环境中启动内置 `low-quality-cleanup` 工作流，提供 `dataset_id` 及可选的 `quality_max`（默认 60 分，包含边界）。命中文件会先隔离，删除前等待人工签批；签批后须返回工作流显式恢复，才能完成质量复查。拒绝签批或未签批的删除计划不会删除文件。网页、CLI 和 API 步骤见[工作流说明](WORKFLOWS.md)。

## Point-cloud operators / 点云算子

PLY supports ASCII, binary little endian and binary big endian. PCD supports ASCII and binary. `binary_compressed` PCD returns an explicit unsupported error. Coordinates `x`, `y`, `z` are required; supported additional scalar fields such as intensity, RGB and labels survive row selection and encoding.

PLY 支持 ASCII、小端二进制和大端二进制；PCD 支持 ASCII 与二进制。PCD `binary_compressed` 明确报不支持。必须包含 `x`、`y`、`z`；强度、RGB、标签等受支持的额外标量字段在选点及编码后保留。

| Operator / 算子         | Behavior / 行为                                                                                                                                                                      |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `pointcloud.probe`      | Format, encoding, fields, counts, finite bounding box, density, invalid/outlier ratios and unit suspicion / 格式、编码、字段、点数、有效坐标范围、密度、无效与离群占比、疑似单位问题 |
| `pointcloud.clean`      | Remove NaN/Inf and optionally clip an inclusive coordinate box / 去除 NaN/Inf，可按含边界坐标框裁剪                                                                                  |
| `pointcloud.downsample` | Deterministic first-point selection in source-unit voxels / 按源坐标单位体素，确定性保留首点                                                                                         |
| `pointcloud.outliers`   | Remove points with excessive mean neighbor distance / 按平均近邻距离剔除离群点                                                                                                       |
| `pointcloud.unit_check` | Flag implausibly large coordinate extents without automatic rescaling / 对过大坐标范围标为疑似错配，不自动换算                                                                       |
| `pointcloud.preview`    | Local top-down PNG colored by height or intensity / 按高度或强度着色的本地俯视 PNG                                                                                                   |

Coordinates alone cannot prove a physical unit. The default unit check flags a largest main-body coordinate extent above 1,000 source units, or an extent near 1,000 times a comparison extent (500–2,000 times by default). Without an explicit `reference_extent`, the comparison is the median of the smaller half of positive extents in the current batch. Configure `expected_max_extent`, `reference_extent`, `scale_ratio` and `scale_tolerance` for the collection context. A warning suggests `1 / scale_ratio`; it never changes coordinates automatically.

仅凭坐标不能证明物理单位。默认单位检查会对主体最大坐标跨度超过 1,000 个源单位、或接近参照跨度 1,000 倍（默认容许 500–2,000 倍）的扫描发出疑似提示。未指定 `reference_extent` 时，参照值取当前批次较小一半正跨度的中位数。可按采集场景配置 `expected_max_extent`、`reference_extent`、`scale_ratio` 和 `scale_tolerance`。提示建议的换算系数为 `1 / scale_ratio`，不会自动修改坐标。

An outlier is a point whose mean distance to its `k` nearest neighbors exceeds `distance_ratio` (default 4) times the median of that distance over the cloud. The median keeps describing the typical spacing while outliers remain a minority, so a clean scan loses no boundary tail and heavy scattered noise does not inflate its own threshold. Clouds whose own density falls off steeply, such as long-range LiDAR, can lose their sparsest far points; raise `distance_ratio` for them. The probe estimates the ratio from at most 8,192 evenly spaced finite points and reports `outlier_sample_count`. The removal operator examines the full cloud: up to 2,048 points it uses exact kNN; larger clouds use a deterministic Morton ordering with up to `2k` candidates on each side (64 total at the default `k=16`). The ordering uses one isotropic grid scale so a thin axis, such as the noise of a flat ground scan, does not scramble locality. Candidates are a subset of all points, so the approximation can only overestimate neighbor distances: points near spatial-order discontinuities may occasionally be rejected.

The bounding box covers every finite point. Density and `body_extent` describe the main body: estimated outliers are excluded, so a few distant strays neither make a dense scan look sparse nor suggest millimeters. Density is estimated main-body points divided by the main-body bounding-box volume, with a width of one source unit on a zero-extent axis; `min_density` (default 1 point per cubic source unit) sets the sparse threshold. While units are suspected, density is not judged, because its unit is itself in doubt. These are geometric quality hints rather than semantic object classifications.

离群点指到 `k` 个最近邻的平均距离超过全云该距离中位数 `distance_ratio` 倍（默认 4 倍）的点。只要离群点仍是少数，中位数就代表典型点间距：干净扫描不会被固定剔除一截边界点，大量散布噪声也不会抬高自己的阈值。自身密度随距离骤降的点云（如远距激光雷达）可能失去最远处最稀的点，可调高 `distance_ratio`。探测算子最多从 8,192 个等间隔有效点估计离群占比，并通过 `outlier_sample_count` 披露采样数。离群去除算子检查全量点：不超过 2,048 点时使用精确 kNN，更大点云使用确定性 Morton 空间顺序，在每侧最多选 `2k` 个候选（默认 `k=16` 时共 64 个候选）。Morton 网格各轴用同一个尺度，扁平地面扫描的薄轴噪声不会打乱空间局部性。候选只是全体点的子集，近似只会高估近邻距离：空间顺序断点附近的点偶尔会被误判为离群。

包围盒覆盖全部有效点；密度和 `body_extent` 描述主体，即剔除估计离群点后的部分，少量远处散点不会让致密扫描显得稀疏，也不会被误判为毫米单位。密度为估计主体点数除以主体包围盒体积，零跨度轴按一个源单位计宽；`min_density`（默认每立方源单位 1 点）为稀疏阈值。单位存疑时不判定密度，因为密度的单位本身不可信。这些信号用于几何质量检查，不代表语义对象分类。

## Pipeline, reports and Web / 流水线、报告与网页

`datakeel.pipeline.media.media_pipeline()` routes images to quality measurement and point clouds through probe, unit check and preview. `media_pipeline(clean=True)` also cleans, downsamples and removes outliers before producing the final preview. Source observations remain available beside processed measurements. Every executed node records the operator version, parameter digest, inputs and outputs in lineage.

`datakeel.pipeline.media.media_pipeline()` 将图片送入质量检查，将点云依次送入探测、单位检查和预览。`media_pipeline(clean=True)` 在生成最终预览前增加清洗、降采样和离群点去除；处理前的测量仍与处理后结果一同保留。每个执行节点在血缘中记录算子版本、参数摘要及输入输出。

Image usability affects completeness. Point-cloud invalid coordinates affect completeness, outliers and low density affect distribution, and suspected unit mismatch affects consistency. Existing annotation and uniqueness dimensions retain their semantics. Reports name the measured cause and include a point-cloud section. A file object's Facts and Quality tabs show its point-cloud inspection and generated preview; an explicitly selected version pins the preview to the same immutable manifest. Missing or failed previews are reported in the page.

图片可用性影响完整性；点云无效坐标影响完整性，离群点和低密度影响分布，疑似单位错配影响一致性。标注与唯一性维度沿用原有含义。报告明确列出测量原因并增加点云专节。文件对象页的“事实”和“质量”标签展示点云探测及已生成的预览，显式选择版本时预览固定到同一不可变清单；预览未生成或加载失败会显示说明。
