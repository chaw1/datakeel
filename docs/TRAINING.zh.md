# 训练集切分与导出

[English](TRAINING.md)

打开数据集的「版本」页签，在「训练集」区域选择不可变源版本，设置训练、验证、
测试比例、随机种子、是否按全部标签分层和可选的元数据组字段。「预览分布」只读计算，
「保存不可变切分」创建挂在版本上的命名快照。同名同策略重试返回原快照；变更策略
需要另起名称。设 `test=0` 可只切两个集合，例如 `train=0.8, val=0.2`，比例之和必须为 1。

「切分来源」和「已保存的切分集合」下拉框均提供中英文显式可访问名称，
与可见标签一致，便于辅助技术识别。

每个样本只属于一个集合。分布表按样本去重统计每个类别，多标签计数之和可以超过样本数。
图条显示类别在集合中的占比。选择另一个已保存切分，可在界面对比分布；成员归属变化
可通过下方的 CLI 或对比 API 查看。

## 分层、按组与可复现性

单标签数据按种子排序，从最大余数配额开始，再用整数运输求解调整。多标签采用迭代
分层：先分配剩余最稀有标签，每放置一个样本，同时更新其全部标签的目标计数，再以整组
转移和交换修正全部标签的配额与占比。内部计算对标签排序、去重；不可变切分仍保留原始
标签及完整标注，各格式导出其支持的标注。

「分层使用的标注类型」可选 `all`（默认）、`classification`、`detection` 或 `spans`。
默认沿用全部标注类型标签的并集；其他选择分别只使用分类标签、检测框类别或文本片段
类别参与分配。所选类型缺失或已审为空时不贡献标签；与原策略一样，纳入全部冻结标注员
的审阅结果。所选类型的每个标签都参与计算，不退回只取首个标签。

选择只改变算法的计算输入，不改成员原始标签、完整标注、组和重复隔离、界面全部标签
分布或导出标注。关闭分层或使用已有目录归属时，它不影响分配。CLI 参数为
`--stratification-source classification`；HTTP、Agent 与 MCP 使用类型化
`request.stratification_source` 字段，HTTP 切分/预览请求体直接携带该字段。
快照冻结这一选择。旧快照缺字段时按 `all` 解释，身份不变，同名重试仍复用原快照；
改选来源须另起名称。默认 `all` 仍使用既有身份摘要。

对于可达输入，目标是每个标签在各集合的数量距比例目标不超过 1 个样本，样本数至少
50 的类别在各集合的占比距全体不超过 2 个百分点。修正先检查这两项，再优化集合总量；
多标签至多追加 16 个由种子确定的起点。这是有界搜索，不是通用整数可行性证明器，
应核对自己数据的实际分布。

显式组始终不可拆分；启用重复隔离时，近重复关系也形成不可拆分的连通分量，整体分配；隔离约束优先于标签平衡和
精确比例。组字段可使用 `capture.session` 或 `metadata.capture.session` 这样的嵌套
路径；字段缺失或为 null 不会把无关样本并成一组。

即使没有分组，小整数集合也可能无解。例如 159 个样本的互斥类别计数 55/52/52，
另有一个全体共有标签，按 80:10:10 切分。共有标签的 ±1 要求训练集大小 127–128，
验证/测试各 15–16；但大小 16 时，5/16 与 6/16 都无法在 55/159 的 2 个百分点内，
故两个小集合只能各 15，迫使训练集为 129，与共有标签配额冲突。超过验证集目标的
原子组也可能使目标不可达。搜索未达到目标本身不能证明无解。结果始终显示实际计数，
不会拆组或暗改声明的策略。

新切分使用 `1.3-iterative-text`，算法版本纳入切分 ID。种子、完整策略、成员身份、
源内容哈希和标注均冻结。包括 `1.2-primary-no-text` 在内的既有命名快照直接读取原文，
不重算、不替换；同名同策略重试仍返回原快照。使用新算法或修订标注时须另建名称。

生成预览或已保存切分中，请求比例大于 0 的集合为空（如 24/0/0）时，分布表会说明：
显式组和已启用的重复隔离约束优先于比例目标，样本少和整数配额也可能导致空集合。
请核对实际数量并尝试其他种子或分组策略；一次结果不能证明不存在其他分配。
主动设为 0 的集合不触发提示，已有目录归属也不会归因于生成算法。

## 泄漏检查

生成切分默认避开重复边，并始终保持显式分组完整。「已有目录归属」读取导入样本的
`train/`、`val/`、`test/` 归属，检查时保留原集合。逐对报告给出两个样本 ID、各自集合、
信号、距离和解释：

| 信号       | 默认规则                       |
| ---------- | ------------------------------ |
| 完全相同   | SHA-256 内容哈希相等           |
| 图片近重复 | 64 位 dHash 的汉明距离不超过 8 |
| 文本近重复 | 64 位归一文本 simhash 的汉明距离默认不超过 3 |
| 组键重叠   | 指定元数据字段的非 null 值相同 |

图片与文本阈值均可独立在 0–64 之间配置。比较复用可选 Rust 后端，未安装时使用结果一致的
精确 Python 比较，不使用可能漏召回的前缀分桶。A–B、B–C 构成一个切分组，但报告不会
凭传递关系虚构 A–C 这一对。图片哈希是相似性启发式，逐对证据应由使用者复核，
不能当作语义等价证明。

文本比较先做 Unicode NFKC 与 casefold，删除全部 Unicode P* 标点、ASCII 标点/符号、空白及零宽 U+200B/U+200C/U+200D/U+2060/U+FEFF，再做一次 NFKC，
使被标点或空白隔开的组合字符重新组合，随后用 SHA-256
散列字符三元组，按频次投票得到 64 位 simhash；不足三个字符的非空文本作为一个特征。
仅改大小写、空白或标点（含词内插入）的变体距离为 0，即使阈值设为 0 仍能召回。
归一后为空则没有 simhash，逐字节相同仍走 SHA-256。归一只用于比较，不改变导出原文
及字符偏移。短文本、三元组多重集相同的重排模板、或删除空格/符号后相同的文本
（如 `C++` 与 `C`）可能碰撞；这是格式/相似性信号，
不是语义等价证明。

短数字模板额外确认：归一后不超过 80 个字符，且替换连续十进制数字后的文字结构相同，
但归一后的数字内容不同时，不判为文本近重复。例如「订单 1001 已发货」和
「订单 1002 已发货」是不同记录。同一数字内容仅大小写、空白或标点不同仍可比较；
更长文本及文字结构不同的样本继续按配置的相似规则判断。新样本只冻结内容和模板的
SHA-256 摘要，不保存归一原文；既有快照缺少这些摘要时沿用原文本比较，不读源文件补造。
阈值 64 除上述模板排除外会匹配所有具有文本哈希的样本对，一般不适用。
其他短文本与模板碰撞仍可能存在。

逐字节相同的文本只报告一对 exact SHA-256 匹配，不重复计为 text 近重复；
源字节不同但仅格式变化的文本仍报告文本信号。

报告的 `checked_signals` 明确实际检查范围。已保存的 `1.2-primary-no-text` 快照继续
只检查原三类信号，不读源文件补造文本哈希；另建命名切分或预览才计算新文本信号。
干净报告只适用于列出的信号与配置阈值。

纯色图额外确认颜色，避免不同颜色具有相同 dHash：缩成 32×32 RGB 后，各通道标准差
均小于 3 为低纹理。如果任意一张为低纹理，另一张也须低纹理，且平均 RGB 每通道差值
不超过 12 才报告近重复。有纹理图片仍使用配置的 dHash 阈值；纯色图缩放、JPEG 重压缩
仍可匹配。

图片任意一边裁剪超过 10% 不在图片近重复检测范围内；这不保证所有较小裁剪都能召回，
仍按现有 dHash 阈值与颜色确认判断。

## 导出训练包

选择已保存切分、格式，以及多份审阅存在时的一名标注员。「审阅导出计划」复用
`export_dataset` 受控动作，冻结版本、切分和对象/字节预算，经现有签批与执行流程
产生包。完成后点击「下载训练包」；每次下载都会重查源数据的当前导出权限。导出回执进入血缘。

| `format`      | 目录与标注约定                                                                                               |
| ------------- | ------------------------------------------------------------------------------------------------------------ |
| `coco`        | `images/<split>/` 和 `annotations/instances_<split>.json`；整数 ID、像素 xywh、area、`iscrowd=0`             |
| `yolo`        | `images/<split>/`、对应 `labels/<split>/*.txt` 和相对路径 `data.yaml`；类别从 0 开始，坐标为归一中心点和宽高 |
| `imagefolder` | `<split>/<class>/<image>`；每张图必须恰好一个分类标签                                                        |
| `hf_imagefolder` | `<split>/<image>` 和 `metadata.jsonl`；无损标量元数据，详见下文 |
| `text_jsonl`  | `<split>.jsonl`，包含原文、分类标签和半开字符偏移片段                                                        |

COCO 的 `images[].file_name` 相对解压后的包根目录，包含 `images/<split>/` 前缀。
使用方应把图片根目录设为解压包根，而不是 `annotations/` 或 `images/<split>/`。
保留现有目录约定，遵循 [pycocotools 将调用方根目录与 `file_name` 拼接的方式](https://github.com/cocodataset/cocoapi/blob/master/PythonAPI/pycocotools/coco.py)；
标注 JSON 所在目录不是图片根目录。

已审空框图片（`boxes=[]`）保留在 COCO images 中，YOLO 对应空 txt。未审框（`boxes=null`）
拒绝导出检测格式，避免把未知当作负样本。YOLO 的所选数据须至少有一个明确的框类别；
COCO 可以表示已审全空、无类别数据，这是合法的交换文档，不能构成有效的零类别训练任务。
非法、越界框拒绝导出；ImageFolder
拒绝缺分类或多标签。文本偏移计 Unicode 字符，不计 UTF-8 字节或 UTF-16 编码单元，
并对未归一化的原文校验范围。
ImageFolder 接受 torchvision 默认后缀：`.jpg`、`.jpeg`、`.png`、`.ppm`、`.bmp`、
`.pgm`、`.tif`、`.tiff`、`.webp`。YOLO 接受 Ultralytics 图片后缀：`.avif`、`.bmp`、
`.dng`、`.heic`、`.heif`、`.jp2`、`.jpeg`、`.jpg`、`.mpo`、`.png`、`.tif`、`.tiff`、
`.webp`。两者均明确拒绝 GIF 等其他后缀，避免标准加载器静默忽略包内图片；不做转码。
导入坐标若仅因浮点还原误差越过像素边界，且误差不超过图像尺寸的四个 ULP，则钳回边界；
明显越界仍拒绝。

HF imagefolder 的 `file_name` 相对所在切分的 `metadata.jsonl`，其余列为标量：
`sample_id`、`annotator_id`、`width`、`height`、`labels_json`、`boxes_json`。
解压后用 `datasets.load_dataset("imagefolder", data_dir="package")` 读取，HF 将 `val`
识别为 `validation`。对两个 `_json` 列执行 `json.loads`，可恢复原类别字符串和像素
`x1,y1,x2,y2` 框；JSON `null` 表示未审，`[]` 表示已审空。使用 JSON 文本列使全空
与非空标注切分的推断 schema 一致，不添加虚假样本。包内 `README.md` 也说明此约定，
不引入 `datasets` 依赖。COCO、YOLO 与 HF imagefolder 共用 EXIF 方向校验：只接受
缺失或恒等方向值 1。方向值 2–8 可能使加载器旋转或镜像像素，导致冻结的原像素框和
尺寸失配；须将源图和标注一起转正后重新导入。导出器不转码，也不暗改框坐标；
拒绝时不产生归档。

| 方向处理方案 | 优点 | 代价 |
| ------------ | ---- | ---- |
| 拒绝非恒等 EXIF（本次选择） | 三种格式保持源字节和冻结标注的坐标系一致 | 有方向信息的来源须先转正再导入 |
| 转正像素并变换框 | 可直接导出有方向信息的来源 | 每种旋转和镜像都须重写像素、尺寸及全部框，并定义新的来源血缘语义 |

选择拒绝可沿用既有 HF 策略，保持原字节导出约定。Pillow 的
[`exif_transpose`](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose)
会按方向变换图像并移除方向元数据；若在此采用它，必须同时实现对应坐标变换，
不能只转图不改框。

训练包目的文件名仅接受区分大小写的 `.tar`、`.tar.gz`、`.tgz`：`.tar` 写未压缩 tar，
后两者写 gzip 压缩 tar。`.zip`、`.json`、单独 `.gz` 或无后缀等名称在训练导出动作准备前
即拒绝；Croissant/OpenLineage 元数据导出的原有文件名行为保持不变。
直接写训练包也执行同一后缀校验。

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

格式规范：[HF imagefolder](https://huggingface.co/docs/datasets/image_dataset)、
[COCO](https://cocodataset.org/#format-data)、
[Ultralytics 检测](https://docs.ultralytics.com/datasets/detect/)、
[Ultralytics 图片格式](https://docs.ultralytics.com/modes/predict/#image-and-video-formats)、
[torchvision ImageFolder 源码](https://docs.pytorch.org/vision/stable/_modules/torchvision/datasets/folder.html)。
