# HTTP API 与流水线参考

[English](API_REFERENCE.md) · [文档中心](README.zh.md) · [架构决策](ARCHITECTURE.md) · [返回首页](../README.zh.md)

启动服务后，FastAPI 自动生成的[本机交互式 API 文档](http://127.0.0.1:8765/api/docs)提供完整的请求与响应 schema。

## 接口总览

| 工作流 | 接口 |
| --- | --- |
| 数据集与导入 | `GET/POST /api/datasets`、`GET /api/datasets/{id}`；导入接收 `{filename, content_base64}` 列表 |
| 版本与下载 | `GET /api/datasets/{id}/versions`、`/files?version={version_id}`、`/files/{file_id}/download` |
| 任务执行 | `POST /api/tasks`、`GET /api/tasks`、`/api/tasks/{id}`、`/api/tasks/{id}/artifacts` |
| 血缘与影响面 | `GET /api/lineage/graph?asset={id}&direction=upstream&depth=3`、`POST /api/lineage/events` |
| 证据 | `POST /api/evidence/query`、`GET /api/evidence/assets/{asset_id}?version_id={version_id}`、`POST /api/evidence/assertions/decide` |
| 证据子图 | `GET /api/lineage/graph?include_semantic=true&asset_id={id}&hops=2&max_nodes=100` |
| 数据目录 | `GET /api/catalog/{collection}`；集合为 `sources`、`tables`、`columns`、`metrics`、`dimensions`、`terms`、`owners`，支持 `limit`、`offset`、`search`、`parent_id`、`source_id` |
| 表与指标详情 | `GET /api/catalog/tables/{asset_id}`、`GET /api/catalog/metrics/{id}`、`GET /api/catalog/metrics/{id}/history` |
| 问数与回放 | `POST /api/ask`、`GET /api/ask/{id}` |
| 目录关系 | `GET /api/catalog/neighbors?asset_id={id}`、`GET /api/catalog/impact?asset_id={id}&max_nodes=100` |
| 目录子图 | `GET /api/lineage/graph?asset_id=retail_revenue&hops=2&max_nodes=30&include_catalog=true` |
| 质量 | `GET /api/datasets/{id}/quality`、`PUT /api/datasets/{id}/quality/config` |
| 治理 | `PUT /api/datasets/{id}/template`、`GET/PUT /metadata`、`GET /metadata/changes`、`GET /compliance` |
| Agent 会话 | `POST/GET /api/agent/conversations`、`GET /api/agent/conversations/{id}`、`POST /api/agent/conversations/{id}/messages`（SSE） |
| Agent 恢复 | `POST /api/agent/conversations/{id}/resume`，请求体 `{plan_id, idempotency_key}`（SSE）；`GET /api/agent/conversations/{id}/audit` 查询恢复审计 |
| 受控动作 | `POST /api/actions/{type}/prepare`、`POST /api/approvals/{plan_id}`、`POST /api/actions/{plan_id}/execute`、`GET /api/actions/runs` |
| 本体与计量 | `GET /api/ontology`、`POST /api/ontology/object-sets/evaluate`、`GET /api/harness/traces`、`GET /api/harness/costs?group_by=conversation` |
| 报告与导出 | `GET /api/datasets/{id}/report`、`GET /api/export?format=croissant&dataset_id={id}` |

## 任务提交与流水线

任务接受 `dataset_id`、`idempotency_key`、可选 `version_id`、`pipeline`、`shards` 和 `queue`。未指定版本时从导入快照重放；指定版本时消费该不可变快照，提交时即冻结输入列表。

- **分片与去重**：默认一个分片保证全数据集去重；显式多分片适合独立文件变换，去重只在各分片内生效，没有跨分片合并去重。
- **队列**：支持 `cpu`、`io`、`gpu`，内置算子提供 CPU/IO 算子。
- **DAG 校验**：类型化 DAG JSON 格式与算子 manifest 见[合同说明](../contracts/README.md)。条件或路由造成空输入时，算子仍记录空批次执行事件；非法 DAG 在入队前拒绝。

## 证据抽取与查询

证据抽取复用 `run_pipeline` 动作：将 `datakeel.pipeline.evidence.evidence_pipeline()` 返回的完整 DAG 作为 `pipeline` 参数，同时传入 `dataset_id` 和 `shards=1`。算子 manifest 列出五个证据算子（`evidence.image_phash`、`evidence.caption_mentions`、`evidence.annotation_labels`、`evidence.label_gap`、`evidence.near_duplicate`）；全局近重复抽取拒绝多分片。省略 `pipeline` 仍使用原有默认算子链。

抽取报告提供整体及每算子的 `inputs`、`skipped_cached`、`extracted`、`failed`。默认证据集首跑为 5,000 次算子输入、4,990 次成功抽取、10 次图像解码失败；内容不变时重跑缓存命中全部 5,000 次输入，抽取为零。缓存键包含实际输入内容、selector、extractor ID/版本、schema 版本及两份证据合同的哈希。只变更 caption 抽取器版本时仅重抽其 1,000 次输入，其余算子命中缓存，旧 caption 断言失效并留下审计。

### ObjectSet 1.1 查询示例

`POST /api/evidence/query` 请求体为平铺的 ObjectSet 1.1 加 `cursor`、`page_size`（默认 50，最多 200），结果按 asset ID 升序，下一页传回 `next_cursor`。从 `GET /api/datasets` 取得配对数据集 ID 后替换下例：

```bash
DATASET_ID="replace-with-paired-dataset-id"
curl --fail http://127.0.0.1:8765/api/evidence/query \
  -H 'Content-Type: application/json' --data-binary @- <<EOF
{
  "schema_version": "1.1",
  "dataset_id": "${DATASET_ID}",
  "split": "val",
  "assertion_filters": [
    {"predicate": "mentions", "concept": "person", "value": "present"},
    {"predicate": "annotated_as", "concept": "person", "value": "present", "operator": "not_exists"}
  ],
  "has_near_duplicate_in": "train",
  "page_size": 20
}
EOF
```

其中 `not_exists` 表示没有匹配的标注断言，包含 `unknown` 未知情况；只查已确认缺口时应要求 `label_gap/person=present`。旧 ObjectSet 1.0 冻结 manifest 仍可按原序列化方式读取。断言过滤在动作准备时求值并冻结结果对象集。

### 语义血缘与投影重建

血缘接口支持 `include_semantic`、`asset_id`、`hops`（1–3）和 `max_nodes`（1–1,000），语义邻居按资产类型及 ID 排序进行确定性 BFS。`near_duplicate_of` 投影为既有 `similar_to` 边类型。抽取事件只引用内容寻址的 knowledge bundle，事件表不写断言正文。重建断言/缓存投影并重放审核审计：

```bash
uv run datakeel rebuild-evidence
```

命令报告包含 `PROJECTOR_VERSION` 的前后规范化哈希，不一致时退出码非零。在手动清空可丢弃投影后，可用 `--expected-hash` 传入此前保存的哈希以对比原状态。

## 语义层与指标 YAML 合同

[语义层](../contracts/semantic-layer/metrics.yaml)刻意区分三个口径：出货额（ERP 出货价，供应链负责人）、销售额（CRM 已入账开票金额，财务负责人）和零售额（已完成订单实付金额，零售运营负责人）。以下简化 YAML 展示初始化空指标目录时的实际 schema：

```yaml
metrics:
  - id: retail_revenue
    name: 零售额
    english_name: Retail revenue
    synonyms: [终端零售额, 实付零售额, 营业额]
    description: 已完成电商订单的实付金额，未冲抵后续退款。
    owner: 零售运营负责人
    version: 1
    measure:
      table: ecommerce/main/orders
      column: ecommerce/main/orders/paid_amount
      aggregation: sum
    filters:
      - column: ecommerce/main/orders/status
        op: eq
        value: completed
    time:
      column: ecommerce/main/orders/date
      granularity: day
    dimensions: [retail_region, retail_channel, retail_category]
    caveats: [合成数据，金额为人民币元；出货额、销售额和零售额不可互换。]
```

- `time` 必填。聚合函数允许 `sum/count/count_distinct/avg/min/max`；过滤字段 `op` 仅允许 `eq/ne/in/gte/lte`，只有 `in` 使用数组值。
- 维度绑定已登记的 `column`，可附静态 `values` 与可选 `value_synonyms`；术语通过 `means: {kind: metric|dimension|column, id: ...}` 指向对象。不支持 `grain` 或 `values_source`。
- 资产 ID 为 `source/schema/table[/column]`，SQLite 的 schema 为 `main`，名称中的分隔符及空白按段 percent-encode。引用缺失时，指标显示 `unresolved` 与原因，并拒绝执行查询。
- 负责人中英文显示元数据单独登记在 [`owners.yaml`](../contracts/semantic-layer/owners.yaml)，按原负责人名称关联。
- 受控指标修改与回滚使用 `update_metric` / `rollback_metric`（术语同理 `update_term` / `rollback_term`）。将 `retail_revenue` 从 `paid_amount` 改为 `list_amount`，同一示例问数结果变为 `5,255,975`，并在 `GET /api/catalog/metrics/retail_revenue/history` 记录新版本。
- 目录源导入使用 `import_catalog` / `restore_catalog`，重建目录投影及规范化哈希校验使用 `uv run datakeel rebuild-catalog`。

## 质量、治理模板与标准导出

- **五维质量评分**：权重为完整性 25、一致性 20、唯一性 15、标注 25、分布健康 15；无标注时默认剔除标注维并重归一，仍返回五维对象。一致性按模态分组，分布健康使用 Shannon 均匀度。例如 `{"min_size_bytes":999999}` 会降低完整性，`{"thresholds":{"excellent":99}}` 可调整等级边界。
- **治理模板**：支持 JSON Schema 或 `fields` 字段定义（必填/枚举/正则），可先绑定模板再补元数据；非法保存整体拒绝，合法保存记录前后值、来源与原因，并刷新目录 40/30/30（目录/命名/元数据）合规分。模板引用限本地 schema。
- **标准导出**：`export --format openlineage` 导出事件数组，逐个元素按官方 RunEvent Schema 校验。Croissant 1.1 描述原始源文件及下载链接。CLI 导出可用 `DATAKEEL_BASE_URL` 指定服务地址，HTTP 导出自动采用请求地址。

## OpenTelemetry 模型 Trace 导出

`datakeel export-traces [--conversation-id ID]` 只读现有 trace 数据库（不 migrate、不写入），同步导出同时携带 [OpenTelemetry GenAI client-inference 语义约定](https://github.com/open-telemetry/semantic-conventions-genai/blob/16f3130892e2e02fa3f0eef72c0e6b554ff08e5c/docs/gen-ai/client-inference.md)（目前为 **Development**）和 OpenInference 属性的 OTLP/HTTP protobuf span。提示词、补全、工具 payload、对话正文、模型路由 JSON 和 exporter 凭证均不导出；span 时间为由结算时间与 latency 重建的近似值。

只有 HTTP 200 且 `rejected_spans=0` 才算接受；命令无后台队列或导出 cursor，重复运行可能在看板产生重复 span：

```bash
# 本地 OTLP Collector
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces \
  uv run datakeel export-traces --conversation-id <id>

# 本地 Phoenix（span 同时带 OpenInference 属性）
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:6006/v1/traces \
  uv run datakeel export-traces --conversation-id <id>

# Langfuse：通用 base endpoint，凭证只放在仓库外环境变量中
export OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=Basic <base64-public-key-secret-key>,x-langfuse-ingestion-version=4'
uv run datakeel export-traces --conversation-id <id>
```
