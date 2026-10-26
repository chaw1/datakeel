# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish generated enterprise cards through the ordinary controlled-action lifecycle."""

from datakeel.actions import service
from datakeel.actions.models import ExecuteRequest
from datakeel.core.data_asset_models import AssetClassification, DataAsset, DataAssetDefinition
from datakeel.core.errors import ExecutionError
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.storage.data_asset_store import get_asset, list_assets
from datakeel.storage.database import Database


def _execute(db: Database, action: str, arguments: JsonDocument) -> str:
    plan = service.prepare_action(db, action, arguments)
    run = service.execute_plan(
        db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    )
    if run.status != "SUCCEEDED" or run.receipt is None:
        raise ExecutionError(run.error or "Asset demo controlled action failed")
    details = JsonDocument.model_validate(run.receipt.quality.get("details"))
    asset_id = details.root.get("asset_id")
    if not isinstance(asset_id, str):
        msg = "Asset demo receipt did not identify its card"
        raise ExecutionError(msg)
    return asset_id


def _publish(db: Database, definition: DataAssetDefinition) -> DataAsset:
    existing = next(
        (
            asset
            for asset in list_assets(db)
            if asset.definition.target == definition.target
            and "asset-demo" in asset.definition.tags
        ),
        None,
    )
    if existing:
        return existing
    asset_id = _execute(
        db,
        "create_data_asset",
        JsonDocument({"definition": definition.model_dump(mode="json")}),
    )
    _execute(db, "publish_data_asset", JsonDocument({"asset_id": asset_id}))
    return get_asset(db, asset_id)


def seed_asset_demo(db: Database, dataset_id: str) -> tuple[DataAsset, ...]:
    """Keep six idempotent cards across all classifications without issuing hidden grants."""
    definitions: tuple[tuple[AssetRef, str, str, AssetClassification], ...] = (
        (AssetRef(asset_id=dataset_id), "生成样本数据集", "Generated sample dataset", "public"),
        (
            AssetRef(asset_type="table", asset_id="ecommerce/main/orders"),
            "终端订单表",
            "Retail orders",
            "internal",
        ),
        (
            AssetRef(asset_type="metric", asset_id="retail_revenue"),
            "零售额",
            "Retail revenue",
            "internal",
        ),
        (
            AssetRef(asset_type="metric", asset_id="shipment_amount"),
            "出货额",
            "Shipment amount",
            "request",
        ),
        (
            AssetRef(asset_type="metric", asset_id="customer_count"),
            "客户数",
            "Customer count",
            "restricted",
        ),
        (
            AssetRef(asset_type="metric", asset_id="refund_amount"),
            "退款额",
            "Refund amount",
            "public",
        ),
    )
    return tuple(
        _publish(
            db,
            DataAssetDefinition(
                target=target,
                name=name,
                name_en=name_en,
                owner="示例企业数据负责人",
                classification=classification,
                tags=("asset-demo", "enterprise"),
                synonyms=(name_en, f"企业{name}"),
                description="完全生成的企业样例; 口径来自登记指标, 卡片不包含真实业务数据。",
                scenarios=("经营分析", "授权流程演示"),
                instructions=(
                    "申请使用时填写操作人和用途, 选择查询/导出/下载范围及期限; "
                    "获批后以同一操作人使用。"
                ),
                sample="区域: 示例区域; 金额: 100(合成、脱敏样例)。",
            ),
        )
        for target, name, name_en, classification in definitions
    )
