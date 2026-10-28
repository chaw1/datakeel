# 训练集切分与导出

[English](TRAINING.md)

打开数据集的「版本」页签，在「训练集」区域选择不可变源版本，设置训练、验证、
测试比例、随机种子、是否按主标签分层和可选的元数据组字段。「预览分布」只读计算，
「保存不可变切分」创建挂在版本上的命名快照。同名同策略重试返回原快照；变更策略
需要另起名称。设 `test=0` 可只切两个集合，例如 `train=0.8, val=0.2`，比例之和必须为 1。

每个样本只属于一个集合。分布表按样本去重统计每个类别，多标签计数之和可以超过样本数。
图条显示类别在集合中的占比。选择另一个已保存切分，可在界面对比分布；成员归属变化
可通过下方的 CLI 或对比 API 查看。

## 分层、按组与可复现性

分层只平衡每个样本的一个主标签，即字典序最小的标签；单标签样本的主标签就是
其唯一标签。不可变切分保留全部标签及完整标注，各导出只写入对应格式支持的标注。
分布表仍统计每个标签；非主标签不承诺平衡或占比误差上限。

独立样本按种子排序，从最大余数配额开始；小集合取整时，有界整数运输求解可调整到
可行的主标签总量。同组和近重复关系的连通分量不可拆分，每个分量整体分配；隔离
约束优先于主标签平衡和精确比例。组字段可使用 `capture.session` 或
`metadata.capture.session` 这样的嵌套路径；字段缺失或值为 null 不会把无关样本并成一组。

组不跨集合的约束优先于比例目标。组比验证集目标还大，或分组互相约束时，
某些比例在数学上不可达，应以分布表中的实际计数为准。切分冻结种子、完整策略、
算法版本、成员身份、源内容哈希和标注。后续导入新标注不会改写旧切分；需另建命名
切分才能使用修订后的标注。

即使没有分组，小整数集合也可能无解。例如三种主标签计数 92/83/68、90:5:5 策略，
不存在正整数验证集大小，能同时使每个主标签计数偏差不超过 1、占比偏差不超过 2 个百分点。
结果始终显示实际计数；无法达到目标也不会拆组或暗改声明的策略。

## 泄漏检查

生成切分默认避开重复边，并始终保持显式分组完整。「已有目录归属」读取导入样本的
`train/`、`val/`、`test/` 归属，检查时保留原集合。逐对报告给出两个样本 ID、各自集合、
信号、距离和解释：

| 信号       | 默认规则                       |
| ---------- | ------------------------------ |
| 完全相同   | SHA-256 内容哈希相等           |
| 图片近重复 | 64 位 dHash 的汉明距离不超过 8 |
| 组键重叠   | 指定元数据字段的非 null 值相同 |

图片阈值可在 0–64 之间配置。比较复用可选 Rust 后端，未安装时使用结果一致的
精确 Python 比较，不使用可能漏召回的前缀分桶。A–B、B–C 构成一个切分组，但报告不会
凭传递关系虚构 A–C 这一对。图片哈希是相似性启发式，逐对证据应由使用者复核，
不能当作语义等价证明。

暂不提供文本相似性检查。文本文件的 SHA-256 完全相同仍会检查，不做文本归一化。
干净报告只覆盖完全相同内容、图片与分组，不能证明不同文本文件之间没有近重复。

纯色图额外确认颜色，避免不同颜色具有相同 dHash：缩成 32×32 RGB 后，各通道标准差
均小于 3 为低纹理。如果任意一张为低纹理，另一张也须低纹理，且平均 RGB 每通道差值
不超过 12 才报告近重复。有纹理图片仍使用配置的 dHash 阈值；纯色图缩放、JPEG 重压缩
仍可匹配。

## 导出训练包

选择已保存切分、格式，以及多份审阅存在时的一名标注员。「审阅导出计划」复用
`export_dataset` 受控动作，冻结版本、切分和对象/字节预算，经现有签批与执行流程
产生包。完成后点击「下载训练包」；每次下载都会重查源数据的当前导出权限。导出回执进入血缘。

| `format`      | 目录与标注约定                                                                                               |
| ------------- | ------------------------------------------------------------------------------------------------------------ |
| `coco`        | `images/<split>/` 和 `annotations/instances_<split>.json`；整数 ID、像素 xywh、area、`iscrowd=0`             |
| `yolo`        | `images/<split>/`、对应 `labels/<split>/*.txt` 和相对路径 `data.yaml`；类别从 0 开始，坐标为归一中心点和宽高 |
| `imagefolder` | `<split>/<class>/<image>`；每张图必须恰好一个分类标签                                                        |
| `text_jsonl`  | `<split>.jsonl`，包含原文、分类标签和半开字符偏移片段                                                        |

已审空框图片（`boxes=[]`）保留在 COCO images 中，YOLO 对应空 txt。未审框（`boxes=null`）
拒绝导出检测格式，避免把未知当作负样本。YOLO 的所选数据须至少有一个明确的框类别；
COCO 可以表示已审全空、无类别数据，这是合法的交换文档，不能构成有效的零类别训练任务。
非法、越界框拒绝导出；ImageFolder
拒绝缺分类或多标签。文本偏移计 Unicode 字符，不计 UTF-8 字节或 UTF-16 编码单元，
并对未归一化的原文校验范围。
导入坐标若仅因浮点还原误差越过像素边界，且误差不超过图像尺寸的四个 ULP，则钳回边界；
明显越界仍拒绝。

`MANIFEST.json` 包含源版本、可选发布、切分 ID、种子、格式及其版本、总文件与标注数、
各集合计数和逐文件源哈希。文件名转换为稳定安全名称。tar 成员按路径排序，所有者、
权限、时间固定；`.tar.gz` 和 `.tgz` 的 gzip 头也固定。同版本、同已保存切分、同标注员、
同格式和压缩方式得到逐字节相同的包，不包含目的文件名或动作时间。无需新增训练库依赖。

## CLI、Agent 和 HTTP

```sh
datakeel training distribution DATASET --version VERSION --train 0.8 --val 0.1 --test 0.1 --seed 42 --json
datakeel training create DATASET --version VERSION --name baseline --group-field capture.session
datakeel training list DATASET --version VERSION
datakeel training leakage DATASET --version VERSION --split-set SPLIT --json
datakeel training compare DATASET LEFT_SPLIT RIGHT_SPLIT
```

不传 `--split-set` 时，`distribution` 预览生成切分，`leakage` 检查目录归属。不传
`--version` 时选择最新不可变版本，并在结果中返回确切 ID。Agent 和 MCP 按需发现
`training_distribution`、`training_leakage`，均只读，返回与 CLI 相同的真实测量。

API 前缀为 `/api/datasets/{dataset}/versions/{version}/training`：

- `GET/POST /splits` 列出或保存切分；`POST /preview` 只计算。
- `GET /splits/{id}` 读取详情；`GET /splits/{id}/leakage` 检查冻结的信号。
- `POST /leakage` 检查预览；`GET /compare?left=ID&right=ID` 对比已保存切分。
- `POST /import-annotations` 导入标准 COCO 或类型化 YOLO，为该版本追加不可变标注批次。
  COCO 可用显式文件名映射解决重命名与同名歧义；YOLO 输入类别表、样本 ID、原图尺寸和逐图标签文本。

导出通过 `POST /api/actions/export_dataset/prepare`，传入 `dataset_id`、`version_id`
（或 `release_id`）、`split_set_id`、`format`，以及可选的 `annotator_id`、`destination`。
原有元数据导出格式保持兼容。完整类型定义见[本机 API 参考](http://127.0.0.1:8765/api/docs)。

格式规范：[COCO](https://cocodataset.org/#format-data)、
[Ultralytics 检测](https://docs.ultralytics.com/datasets/detect/)。
