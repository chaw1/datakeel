# Image and point-cloud quality / 图片与点云质量

Datakeel measures image usability and point-cloud geometry with local Pillow and NumPy operators. No model, network service or additional runtime package is required. Generated measurements feed the existing five quality dimensions, sample selection, reports and append-only lineage.

Datakeel 使用本地 Pillow 和 NumPy 算子检查图片可用性与点云几何质量，无需模型、网络服务或额外运行时依赖。测量结果进入既有五维评分、样本筛选、报告及追加式血缘。

## One-command demonstration / 一条命令演示

From the repository root, choose a new or empty local output directory:

在仓库根目录执行，输出目录须为新目录或空目录：

```sh
uv run python scripts/demo_media.py --output /tmp/datakeel-media-demo
```

The command creates five indoor scans: a room in ordinary coordinate units, a millimeter-scaled copy, a scan with scattered strays and a floating cluster, a scan with NaN/Inf coordinates and a sparsely sampled room. Eight generated PNGs cover a clear image, two blur strengths, overexposure, underexposure, noise, low resolution and a solid color. The demo declares its scans as `terrestrial`, so sparse coverage is judged rather than only hinted.

脚本生成五份室内扫描：普通坐标单位的房间、放大到毫米尺度的副本、含散布离群点和一团悬空点的扫描、含 NaN/Inf 坐标的扫描以及稀疏采样的房间；另生成八张 PNG，覆盖清晰、两档模糊、过曝、过暗、噪声、低分辨率和纯色。演示把扫描声明为 `terrestrial`（地面架站扫描），因此稀疏会被判定，而不只是提示。

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

`image.quality` emits five scores, per-check failures and explanations, plus an overall score. Decode corrects EXIF orientation first, and 16-bit grayscale is scaled by its bit depth to 8-bit levels, so a normal 16-bit PNG is not read as white. Each check has configurable parameters; the overall score reflects the weakest usability check so a severe defect remains eligible for the existing approved low-quality cleanup workflow.

- **Blur** is the square root of Laplacian energy over gradient energy at a common analysis size (larger images are reduced to `analysis_size`; smaller ones are measured natively, not enlarged). Scaling all intensities, as low contrast, haze or underexposure do, scales both energies alike, so the ratio depends on edge width rather than edge strength. The expected 8-bit rounding energy is removed first, so faint blurred content cannot look sharp through its stair steps. A crisp edge scores about 1.4; `min_sharpness` defaults to 1. The old absolute Laplacian variance limit remains available as `blur_threshold` and is off by default.
- **Exposure** fails on a mean outside `[min_brightness, max_brightness]`, on clipped dark or bright fractions above `max_clipped_fraction`, or on a 99.9th-percentile highlight below `min_highlight` (120), which catches moderate underexposure whose mean still looks acceptable. A failed exposure or a near-solid image is reported as that cause alone: blur is not judged on it.
- **Noise** fails on a robust native-pixel sigma above `max_noise_sigma`, or on an impulse pixel fraction above `max_impulse_fraction` (0.3%). An impulse differs from its 3×3 median by more than `impulse_level` and from every neighbor by more than half of it, so salt-and-pepper pixels count but one-pixel lines and text strokes do not. Large images are sampled on at most 16 native tiles of 256 pixels.
- **Resolution** and **solid color** use the shortest side and the largest channel standard deviation.

Defaults were set on generated natural-texture scenes, including fog, snow, minimal compositions, dark scenes and low-contrast copies at a quarter of normal contrast, each also saved as JPEG. Known limits: below about a quarter of normal contrast, 8-bit rounding leaves too little edge energy and a sharp image can be called blurry; strong JPEG compression smooths Gaussian noise below the sigma limit.

`image.quality` 输出模糊、曝光、噪声、分辨率、纯色五项得分、各项是否失败及原因，并给出总分。解码先校正 EXIF 方向；16 位灰度按位深缩放到 8 位，正常的 16 位 PNG 不会被读成全白。各项阈值可配置；总分取可用性最弱项，使单项严重缺陷仍能进入既有低质样本筛选及签批清理流程。

- **模糊**：在统一分析尺寸下（大图缩小到 `analysis_size`，小图按原尺寸测量、不放大）取拉普拉斯能量与梯度能量之比的平方根。低对比度、雾或欠曝会把所有亮度等比缩小，两种能量同比变化，所以该比值只取决于边缘宽度，不取决于边缘强弱。计算前先扣除 8 位取整带来的期望能量，避免淡而模糊的内容靠台阶状取整显得清晰。清晰边缘约 1.4，`min_sharpness` 默认 1。旧的拉普拉斯方差绝对阈值保留为 `blur_threshold`，默认关闭。
- **曝光**：均值超出 `[min_brightness, max_brightness]`、暗部或亮部截断占比超过 `max_clipped_fraction`、或 99.9 分位高光低于 `min_highlight`（120）时不合格；最后一条用来抓均值看似正常的中度欠曝。曝光不合格或近纯色时只报该原因，不再同时判模糊。
- **噪声**：原生像素稳健 sigma 超过 `max_noise_sigma`，或脉冲像素占比超过 `max_impulse_fraction`（0.3%）时不合格。脉冲像素与 3×3 中值之差超过 `impulse_level`，且与每个邻点之差都超过其一半，所以椒盐点会被计入，单像素线条和文字笔画不会。大图最多抽 16 块 256 像素的原生分块测量。
- **分辨率**和**纯色**分别看最短边和各通道标准差的最大值。

默认值在生成的自然纹理场景上定出，包括雾、雪、极简构图、暗场景，以及对比度降到四分之一的副本，每张同时存成 JPEG 复测。已知局限：对比度低于正常的约四分之一时，8 位取整后剩下的边缘能量太少，清晰图可能被判模糊；强 JPEG 压缩会把高斯噪声抹平到 sigma 阈值以下。

Complete the measurement pipeline before starting the bundled `low-quality-cleanup` workflow in the same dataset environment. Supply `dataset_id` and, optionally, `quality_max` (default 60, inclusive). Matching files are quarantined first; deletion waits for human approval. Return to the workflow and explicitly resume it to finish the quality recheck. Rejected or unsigned deletion plans do not delete files. See [workflow instructions](WORKFLOWS.md) for the Web, CLI and API steps.

先完成测量流水线，再在同一数据集环境中启动内置 `low-quality-cleanup` 工作流，提供 `dataset_id` 及可选的 `quality_max`（默认 60 分，包含边界）。命中文件会先隔离，删除前等待人工签批；签批后须返回工作流显式恢复，才能完成质量复查。拒绝签批或未签批的删除计划不会删除文件。网页、CLI 和 API 步骤见[工作流说明](WORKFLOWS.md)。

## Point-cloud operators / 点云算子

PLY supports ASCII, binary little endian and binary big endian. PCD supports ASCII and binary. `binary_compressed` PCD returns an explicit unsupported error. Coordinates `x`, `y`, `z` are required; supported additional scalar fields such as intensity, RGB and labels survive row selection and encoding.

PLY 支持 ASCII、小端二进制和大端二进制；PCD 支持 ASCII 与二进制。PCD `binary_compressed` 明确报不支持。必须包含 `x`、`y`、`z`；强度、RGB、标签等受支持的额外标量字段在选点及编码后保留。

| Operator / 算子         | Behavior / 行为                                                                                                                                                                                                 |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pointcloud.probe`      | Format, encoding, fields, counts, finite bounding box, invalid and outlier ratios with an interval, main-body extent, relative spacing and unit suspicion / 格式、编码、字段、点数、有效范围、无效与离群占比及区间、主体跨度、相对点距、疑似单位问题 |
| `pointcloud.clean`      | Remove NaN/Inf and optionally clip an inclusive coordinate box / 去除 NaN/Inf，可按含边界坐标框裁剪                                                                                                             |
| `pointcloud.downsample` | Deterministic first-point selection in source-unit voxels / 按源坐标单位体素，确定性保留首点                                                                                                                    |
| `pointcloud.outliers`   | Remove isolated points and separated clusters with the probe's rule / 用与探测相同的规则剔除孤立点和分离的点团                                                                                                 |
| `pointcloud.unit_check` | Suspect an extent beyond the declared sensor form; hint at a batch scale mismatch / 跨度超出声明采集形式时判单位存疑；与批次差约千倍时只给提示                                                                 |
| `pointcloud.preview`    | Local top-down PNG colored by height or intensity / 按高度或强度着色的本地俯视 PNG                                                                                                                              |

### Outliers / 离群点

Scans are dense near the instrument and sparse on far or grazing surfaces, so one cloud-wide spacing cut would reject far walls and keep strays near the scanner. Each point is instead compared with its own neighbors. With `k = neighbors` (12), a point is **isolated** when its mean distance to its `k` nearest neighbors exceeds `local_ratio` (3) times the median of the same measure over those neighbors, and its nearest-neighbor distance does too. The second test keeps short lidar ring fragments and thin poles, whose next point is close, from looking isolated.

Groups of strays are each other's neighbors and pass that test, so points are also joined into components by links no longer than `link_ratio` (3) times the smaller local spacing. Every component other than the largest is a **separated cluster** when:

- its median spacing exceeds `sparse_cluster_ratio` (10) times that of the outside points its members neighbor, which catches strays spread far around a scene however many there are; a group with no outside neighbor at all is compared with the main body instead, unless it is a piece of surface; or
- it is small (fewer than the larger of `min_cluster_points`, 50, and `min_cluster_fraction`, 1% of the cloud) and no other point lies within `cluster_gap` (5) times its link spacing. A piece of scanned surface, thin in some direction (smallest spread below a fifth of its largest), must also be more than twice its own extent away, so ring segments, far wall patches and a cup on a table stay. A stack of repeated coordinates uses the cloud's typical nonzero spacing.

A file gets the `pointcloud_outlier_ratio` issue only when its flagged ratio exceeds `max_outlier_ratio` (0.07%). Up to 500,000 finite points are analysed in full. Larger files use a seeded random point from each of 500,000 equal Morton-order strata, so every region keeps its share; the probe then reports a 95% Wilson interval, and only its lower bound is compared with the limit, so sampling error alone cannot raise an issue. `pointcloud.outliers` always analyses every point.

Neighbors are exact up to 2,048 points. Larger clouds take each point's `k` predecessors and successors along three Morton curves on one isotropic grid, offset by 0, 1/6 and 1/3 of the cloud, and keep the `k` closest. A window can only miss closer points, so distances are never underestimated. On a generated indoor scan the three curves found every nearest neighbor and kept the mean neighbor distance within 2% for 95% of points; one curve alone was 20% high for a typical point.

### Coverage, units and failed files / 稀疏、单位与失败文件

`relative_spacing` is the median nearest-neighbor distance of the main body divided by its extent (corrected by the square root of the sampling fraction when sampled). It does not depend on the unit, so a part in millimeters measures like the same part in meters. The `sensor` parameter declares the capture form and selects defaults:

| `sensor`        | Maximum extent (source units) | Maximum relative spacing | Sparse coverage |
| --------------- | ----------------------------- | ------------------------ | --------------- |
| `unknown`       | 1,000                         | 0.01                     | hint only       |
| `terrestrial`   | 1,000                         | 0.01                     | judged          |
| `vehicle_lidar` | 1,000                         | 0.005                    | judged          |
| `depth_camera`  | 50                            | 0.01                     | judged          |
| `object`        | 10                            | 0.01                     | judged          |

Clean generated captures of each form measure about a quarter of these spacing limits. `max_relative_spacing` overrides the limit and is always judged; `expected_max_extent` overrides the extent.

Coordinates alone cannot prove a physical unit. Only a main-body extent beyond the maximum for the declared form is **unit in doubt** (`pointcloud_unit`, consistency), with the extent, form, limits and a suggested `1 / scale_ratio` as evidence. Sparse coverage is not judged while the unit is in doubt, and no other penalty follows from it. An extent near `scale_ratio` (1,000) times the batch reference (500–2,000 times by default; the reference is `reference_extent` or the median of the smaller half of the batch) is only a hint (`pointcloud_unit_hint`, information, no penalty) that names the factor toward the reference, because a batch may legitimately mix a small part and a whole room. Coordinates are never changed.

A file that cannot be read or validated is kept in the output with the operator and reason under `pointcloud_error`; the other files are processed. The operator result then has `partial: true`, `failed_count` and `failed_files`, later point-cloud steps pass the failed file through untouched, and the report lists it as a `pointcloud_unreadable` error with zero completeness.

Defaults were calibrated only on generated ray-cast scans with density gradients: indoor terrestrial scans at three resolutions, 16- to 64-line vehicle lidar, depth cameras at three tilts, and a structured-light part in meters and millimeters. No clean scan had more than 0.04% of points flagged; every scan with 0.5% scattered outliers had at least 0.16% flagged; strays far around a scene and floating groups of 30 to 120 points were all found. Known limits: strays scattered inside a densely scanned volume are partly masked, because a stray near a surface has close neighbors (20–40% of 2% scattered strays were flagged, still far above the file limit); a cluster larger than 1% of the cloud is only found if it is much sparser than its surroundings; a millimeter part with an undeclared sensor is not suspected, so declare `object`.

扫描在仪器附近很密，在远处或掠射面上很稀，用全云统一的点距阈值会把远处墙面剔掉，却留下仪器旁的散点。因此每个点只和自己的邻点比较。设 `k = neighbors`（12）：一个点到 `k` 个最近邻的平均距离超过这些邻点同一指标中位数的 `local_ratio`（3）倍，且最近邻距离也超过时，判为**孤立点**。第二个条件让激光雷达短环段和细杆不被误判——它们紧挨着下一个点。

成团的散点彼此互为邻点，能躲过上面的检验，所以还要把长度不超过较小局部点距 `link_ratio`（3）倍的近邻连成连通块。除最大块外，满足下列任一条件的块判为**分离点团**：

- 块内点距中位数超过其成员所邻接的块外点点距中位数的 `sparse_cluster_ratio`（10）倍——无论数量多少，都能抓住散布在场景远处的散点；若块的邻点全在块内，则改与主体比较，但薄片状的块（一片表面）除外；
- 或块很小（少于 `min_cluster_points` 50 与 `min_cluster_fraction` 1% 中的较大者），且其连线点距 `cluster_gap`（5）倍范围内没有其他点。在某个方向很薄的扫描表面碎片（最小展布不到最大的五分之一）还须离开其他点超过自身跨度的两倍，所以环段、远处墙面碎片、桌上的杯子都会保留。重复坐标堆成的点团用全云典型非零点距。

离群占比超过 `max_outlier_ratio`（0.07%）时，文件才记 `pointcloud_outlier_ratio` 问题。有效点不超过 50 万时全量分析；更大的文件按 Morton 顺序等分 50 万层，每层用固定种子随机取一点，使各区域按比例入样，并报告 95% Wilson 区间，只用区间下界与阈值比较，抽样误差本身不会触发问题。`pointcloud.outliers` 总是全量分析。

不超过 2,048 点时近邻精确求解。更大的点云沿三条 Morton 曲线（同一各向同性网格，分别偏移 0、1/6、1/3 个云尺度）取每个点前后各 `k` 个候选，保留最近的 `k` 个。窗口只可能漏掉更近的点，因此距离不会被低估。在生成的室内扫描上，三条曲线找到了全部最近邻，95% 的点平均近邻距离误差在 2% 以内；只用一条曲线时，典型点偏高 20%。

`relative_spacing` 是主体最近邻距离中位数除以主体跨度（抽样时按抽样比例的平方根修正），与单位无关，毫米单位的零件和米单位的同一零件测得一样。`sensor` 参数声明采集形式并选择默认值：`unknown` 最大跨度 1,000、相对点距上限 0.01、稀疏只提示；`terrestrial` 1,000 / 0.01、判定；`vehicle_lidar` 1,000 / 0.005、判定；`depth_camera` 50 / 0.01、判定；`object` 10 / 0.01、判定。各形式的干净生成扫描约为这些点距上限的四分之一。`max_relative_spacing` 可覆盖上限且总会判定，`expected_max_extent` 可覆盖跨度上限。

仅凭坐标不能证明物理单位。只有主体跨度超过声明形式的上限才判**单位存疑**（`pointcloud_unit`，计入一致性），证据包括跨度、形式、上限和建议系数 `1 / scale_ratio`；单位存疑时不判稀疏，也不连带其他扣分。跨度约为批次参照值 `scale_ratio`（1,000）倍（默认容许 500–2,000 倍；参照值为 `reference_extent`，未指定时取批次较小一半跨度的中位数）只给提示（`pointcloud_unit_hint`，信息级，不扣分），并给出朝参照值换算的系数，因为一个批次里本来就可以同时有小零件和整间房。坐标不会被修改。

无法读取或校验的文件保留在输出中，`pointcloud_error` 记录出错算子和原因，其余文件照常处理。算子结果带 `partial: true`、`failed_count` 和 `failed_files`，后续点云步骤原样跳过该文件，报告将其列为 `pointcloud_unreadable` 错误，完整性记零。

默认值只在带密度梯度的生成光线投射扫描上校准：三种分辨率的室内架站扫描、16 至 64 线车载激光雷达、三种俯角的深度相机，以及米和毫米两种单位的结构光零件。干净扫描被标记的点都不超过 0.04%；含 0.5% 散布离群点的扫描至少标出 0.16%；场景远处的散点和 30 至 120 点的悬空点团全部找到。已知局限：散布在密集扫描空间内部的散点会被部分掩盖，因为靠近表面的散点本身有近邻（2% 散点中约 20–40% 被标出，仍远超文件阈值）；超过全云 1% 的点团只有明显比周围稀疏时才会被找到；未声明采集形式的毫米零件不会被判单位存疑，需要声明 `object`。

## Pipeline, reports and Web / 流水线、报告与网页

`datakeel.pipeline.media.media_pipeline()` routes images to quality measurement and point clouds through probe, unit check and preview. `media_pipeline(clean=True)` also cleans, downsamples and removes outliers before producing the final preview. Source observations remain available beside processed measurements. Every executed node records the operator version, parameter digest, inputs and outputs in lineage.

`datakeel.pipeline.media.media_pipeline()` 将图片送入质量检查，将点云依次送入探测、单位检查和预览。`media_pipeline(clean=True)` 在生成最终预览前增加清洗、降采样和离群点去除；处理前的测量仍与处理后结果一同保留。每个执行节点在血缘中记录算子版本、参数摘要及输入输出。

Image usability affects completeness. Point-cloud invalid coordinates and unreadable files affect completeness, outliers and judged sparse coverage affect distribution, and a unit in doubt affects consistency; sparse and unit hints are information only. Existing annotation and uniqueness dimensions retain their semantics. Reports name the measured cause and include a point-cloud section. A file object's Facts and Quality tabs show its point-cloud inspection and generated preview; an explicitly selected version pins the preview to the same immutable manifest. Missing or failed previews are reported in the page.

图片可用性影响完整性；点云无效坐标和无法读取的文件影响完整性，离群点和经判定的稀疏影响分布，单位存疑影响一致性；稀疏提示和单位提示只作信息，不扣分。标注与唯一性维度沿用原有含义。报告明确列出测量原因并增加点云专节。文件对象页的“事实”和“质量”标签展示点云探测及已生成的预览，显式选择版本时预览固定到同一不可变清单；预览未生成或加载失败会显示说明。
