# 数据集版本对比与交付

[English](RELEASES.md) · [演示导览](DEMO.md)

从 **数据库 → 数据集 → 版本** 选择同一数据集的两个版本，点击 **对比版本**。五类结果为新增、删除、内容变更（SHA-256 改变）、仅元数据变更、未变。每类显示完整计数，文件清单分页加载，同时展示标注数、标签数、文件质量分均值和证据决策统计的前后变化。质量分按版本摘要中登记的统计口径计算。

旧版本保留文件清单，但没有历史治理快照。对比质量分按数据集当前的质量配置计算；证据决策摘要使用各版本关联证据当前的活跃决策状态。

本地命令示例：

```bash
uv run datakeel version-diff DATASET_ID BEFORE_VERSION AFTER_VERSION --limit 50 --category content_changed --json
```

用 `--offset` 翻页；不指定 `--category` 时返回混合分类页。API 为 `GET /api/datasets/{dataset}/diff?before={version}&after={version}&offset=0&limit=50`，跨数据集的版本会被拒绝。文件按清单中的文件 ID 对齐：相同 ID 先比 SHA-256，再比元数据；具有新 ID 的派生产物算新文件。

## 发布与查看

在 **版本 → 发布版本** 选择来源版本，输入 `v1.2.0` 等语义化标签及发布说明，点击 **审阅发布计划**。检查冻结参数、文件影响、摘要和不可逆提示后，点击 **签批并发布版本**。准备计划不会发布；签批只适用于这一份冻结计划，待办也会出现在 **审批待办**。

发布记录出现在列表中。展开标签可查看来源版本、清单 SHA-256、说明、总字节数和分页冻结文件。发布冻结的是准备发布计划时的当前治理元数据、质量测量及证据决策摘要。发布后的文件、元数据和哈希均不可修改；后续修改须生成新版本并再次发布，原有生成版本流程保持兼容。

自动化继续使用受控动作协议：`POST /api/actions/publish_release/prepare`，参数为 `dataset_id`、`version_id`、`tag`、`notes`；随后在 `POST /api/approvals/{plan_id}` 签批，再通过 `POST /api/actions/{plan_id}/execute` 执行。签批和执行须携带返回的计划摘要，执行使用该计划的 operation ID。查询接口为 `GET /api/datasets/{dataset}/releases`、`GET /api/releases/{release}` 和 `GET /api/releases/{release}/files?offset=0&limit=50`。

## 导出与离线对账

发布详情中的 **导出交付包** 下载 gzip tar 包。本地命令可导出压缩包或新目录：

```bash
uv run datakeel release-export RELEASE_ID --output delivery.tar.gz
uv run datakeel release-export RELEASE_ID --output delivery-directory
```

对应 HTTP 接口为 `POST /api/releases/{release_id}/export`，返回媒体类型为 `application/gzip` 的 tar 压缩包。

交付包包含：

- `MANIFEST.json`：相对路径、字节数、SHA-256、媒体类型、来源版本、血缘引用、标注及标签数、元数据及必填字段，以及规范化清单哈希。
- `RECORDS.json`：收货侧独立核对的数据集元数据，以及逐文件元数据、标注及标签统计和血缘。
- `files/`：实际文件内容。

两个 JSON 文件须与文件内容一同交付。路径均为相对路径，不携带凭证或内部物理存储位置。元数据按字段角色和取值结构过滤：去掉声明为位置的字段（`path`、以 `path` 结尾的字段如 `source_path`、`object_key`、`storage_uri`）、凭证字段、`file://` 或 `s3://` 等存储 URI，以及带凭证的 URL；其他取值原样保留，以 `/` 开头的标签（如 `/m/01yrx`）不会被删除，也计入标签数。导出时根据 [contracts/delivery-manifest.schema.json](../contracts/delivery-manifest.schema.json) 校验清单。清单哈希用于发现清单损坏，不是证明发件人身份的数字签名；需要核验真实性时另行保留可信哈希副本。

文件路径使用序号目录及百分号编码后的文件名，过长编码名会缩短并附加摘要后缀。请按 `MANIFEST.json` 登记的原样路径核对，不要先解码或重命名。Web 中的来源发布快照哈希与交付清单规范化哈希覆盖不同序列化内容，不能互相替代。交付清单哈希使用对象键排序、紧凑分隔符及不转义 Unicode 的 UTF-8 JSON，仅排除顶层 `manifest_sha256` 字段，导出会写入 schema 默认值，对账按实际收到的字段计算，删除默认字段也会被发现；比较交付清单时须使用预期交付清单中的哈希。

收货方安装 Datakeel 后即可运行下列命令，无须连接 API、数据库、对象存储或模型服务：

```bash
datakeel reconcile delivery.tar.gz --manifest MANIFEST.json
datakeel reconcile delivery-directory --manifest MANIFEST.json --json
```

默认清单路径相对于交付包解析。人类输出包含中英文，`--json` 提供结构化报告。六类全通过时退出码为 `0`，发现差异时为 `1`，无法读取或校验交付包、清单时为 `2`。无效输入的 JSON 输出为 `error: "invalid_delivery"` 及错误类别 `reason`，不会回显输入内容。六类分别检查文件数；总字节数和逐文件大小；SHA-256；标注及标签数；必填元数据字段和取值；指向已登记来源版本的血缘引用。元数据及标注检查将 `RECORDS.json` 与 `MANIFEST.json` 对比，不会从任意媒体内容中推断标注语义；缺少收货记录会失败。

标注统计优先使用元数据中明确提供的非负整数 `annotation_count` 或 `label_count`；否则依次查看复数集合（`annotations`、`labels`）和单数集合（`annotation`、`label`）：列表取长度，存在的非空标量或对象计为一，没有登记值计为零。收货记录包含这些字段时还会核对由集合推得的统计与声明数量。明确的数量字段具有优先权，即使同时存在集合也不被覆盖；集合被改动仍会由元数据比较独立发现。

元数据检查覆盖数据集和文件字段、必填字段是否存在以及完整 JSON 值。对象键顺序不影响结果，数组顺序及标量表示影响结果，例如 `true`、`1`、`1.0` 和 `"1"` 不等同。若预期值也是 JSON `null`，必填字段允许取 `null`；此检查不附加业务上的非空约束。

故意破坏一个副本以验证发现差异的能力：

```bash
mkdir received
tar -xzf delivery.tar.gz -C received
python3 - <<'PY'
import json
from pathlib import Path

root = Path("received")
manifest = json.loads((root / "MANIFEST.json").read_text())
payload = root / manifest["files"][0]["path"]
with payload.open("r+b") as stream:
    first = stream.read(1)
    stream.seek(0)
    stream.write(bytes([first[0] ^ 1]) if first else b"x")
PY
datakeel reconcile received --manifest MANIFEST.json
```

哈希分类会指出文件路径和预期、实际值。非空文件只替换一个字节时长度不变，因此字节数分类仍通过。练习元数据、标注或血缘故障时，修改 `RECORDS.json` 对应记录，保留作为预期的原清单。

## 存档平台侧对账

在发布详情点击 **核对存储对象**，平台读取实际存储对象并保存相同的六类结果及差异，刷新页面后仍可查看。API 为 `POST /api/releases/{release}/reconcile` 和 `GET /api/releases/{release}/reconciliations`；本地命令：

```bash
uv run datakeel release-reconcile RELEASE_ID --json
```

## 分片上传与断点续传

向 `POST /api/uploads` 提交 `idempotency_key`、`name`、`filename`、`total_bytes`、完整源文件的 `sha256`、`chunk_bytes` 和可选 `metadata`，保存返回的上传 ID。通过 `GET /api/uploads/{id}` 获取 `received_chunks` 和 `missing_chunks`，新客户端只补缺失分片。分片编号从零开始，通过 `PUT /api/uploads/{id}/chunks/{ordinal}` 发送精确大小的原始字节，设置 `Content-Type: application/octet-stream`。最后调用无请求体的 `POST /api/uploads/{id}/complete` 校验并导入；成功回执包含 `COMPLETE` 状态及 `dataset_id`。

相同分片重传会合并，内容冲突的重复分片会拒绝；允许乱序到达。同一上传的重叠写入返回 `409`，客户端可在前一写入完成后重试。同一个初始化幂等键恢复同一声明，修改声明返回 `409`；不同键代表独立导入意图。完成请求可重复调用。导入前检查整文件 SHA-256，提交数据集事务前再读回实际存储对象核对哈希。大小错误、缺片或哈希不符返回 `422`，不会创建数据集；不存在的上传 ID 返回 `404`。

配置上限为 `DATAKEEL_UPLOAD_MAX_CHUNK_BYTES`（默认 8 MiB，最高 64 MiB）、`DATAKEEL_UPLOAD_MAX_CONCURRENCY`（默认 4，最高 32）和 `DATAKEEL_UPLOAD_MAX_FILE_BYTES`（默认 5 GiB，最高 1 TiB）。最多 100,000 个分片，选择分片大小时须满足这一限制；超出并发写入限制返回 `409`。

分片暂存于配置的 `DATAKEEL_HOME`，完成或失败后仍保留；本版没有自动过期清理或清理接口。磁盘容量须覆盖保留分片及整文件临时组装。持久文件系统不变时，客户端或进程重启后仍可续传。多个 API 主机须共用暂存卷和数据库，或将同一上传固定路由至原主机；只共用 PostgreSQL 不会共享分片字节。进程锁防止重叠写入，不负责复制暂存文件。

使用 `npm --prefix web run smoke:release -- http://127.0.0.1:8816 OUTPUT_DIRECTORY` 重放发布浏览器流程：创建生成样本、对比两个版本、从界面签批发布、下载并核对交付包、修改一个字节，最后确认平台存档报告刷新后仍在。截图及结构化结果写入指定输出目录。脚本仅允许请求给定回环地址，要求浏览器零错误。
