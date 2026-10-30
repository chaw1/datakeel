# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bilingual phrases and examples for every controlled action outside production.

Same format as ``PRODUCTION_LANGUAGE``: (Chinese phrase, English phrase, Chinese example,
English example). The one-sentence entry reads these only through the action registry.
"""

ACTION_LANGUAGE: dict[str, tuple[str, str, str, str]] = {
    "clean_training_data": (
        "发布清洗后的训练版本",
        "publish cleaned training data",
        "按刚才的训练数据体检结果发布清洗后的新版本",
        "Publish the cleaned training version from the last governance dry run",
    ),
    "submit_custom_operator": (
        "提交自定义算子",
        "submit custom operator",
        "提交这段 Python 代码作为自定义算子等审批",
        "Submit this Python code as a custom operator for review",
    ),
    "create_data_asset": (
        "创建数据资产卡片",
        "create data asset",
        "给销售明细数据集建一张资产卡片草稿",
        "Create a draft asset card for the sales dataset",
    ),
    "update_data_asset": (
        "修改数据资产卡片",
        "update data asset",
        "把这张资产卡片的负责人改成小李",
        "Change the owner on this asset card to Li",
    ),
    "publish_data_asset": (
        "上架数据资产",
        "publish data asset",
        "把这张资产卡片发布到资产市场",
        "Publish this asset card to the market",
    ),
    "withdraw_data_asset": (
        "下架数据资产",
        "withdraw data asset",
        "把这张资产卡片从资产市场下架",
        "Withdraw this asset card from the market",
    ),
    "decide_asset_application": (
        "审批资产申请",
        "decide access application",
        "通过小王对这个数据集的使用申请",
        "Approve Wang's access application for this dataset",
    ),
    "revoke_asset_grant": (
        "撤销资产授权",
        "revoke access grant",
        "撤销外包组对这个数据集的访问授权",
        "Revoke the contractor team's access grant to this dataset",
    ),
    "annotation_acceptance": (
        "标注抽检验收",
        "accept annotations by sampling",
        "按抽样结果验收这批标注并归档签字",
        "Accept this annotation batch from the inspected sample and archive it",
    ),
    "quarantine_files": (
        "隔离文件",
        "quarantine files",
        "把这个数据集里质量低于 60 的文本隔离",
        "Quarantine text files with quality below 60 in this dataset",
    ),
    "unquarantine_files": (
        "取消隔离",
        "unquarantine files",
        "把昨天误隔离的这批图片放出来",
        "Release these images from quarantine",
    ),
    "create_version_from_selection": (
        "用选中文件建新版本",
        "create version from selection",
        "用质量高于 80 的文件建一个新版本",
        "Create a new version from files with quality above 80",
    ),
    "run_pipeline": (
        "运行处理流水线",
        "run pipeline",
        "对这个数据集最新版本跑一遍默认处理流水线",
        "Run the default pipeline on the latest version of this dataset",
    ),
    "save_metadata": (
        "保存数据集元数据",
        "save dataset metadata",
        "把这个数据集的负责部门元数据改成运营中心",
        "Set this dataset's owning department metadata to Operations",
    ),
    "delete_files": (
        "删除文件",
        "delete files",
        "删除这批选中的低质量文件",
        "Delete the selected low-quality files",
    ),
    "export_dataset": (
        "导出数据集",
        "export dataset",
        "把这个版本按 COCO 格式导出",
        "Export this version in COCO format",
    ),
    "decide_assertions": (
        "审核证据断言",
        "review assertions",
        "把这几条夜景断言标成已确认",
        "Mark these night-scene assertions as confirmed",
    ),
    "import_catalog": (
        "导入元数据目录",
        "import catalog",
        "从 dbt 的 manifest 导入一份数据目录快照",
        "Import a catalog snapshot from the dbt manifest",
    ),
    "confirm_metric_draft": (
        "确认指标草稿",
        "confirm metric draft",
        "确认刚导入的出货额指标草稿",
        "Confirm the imported shipment value metric draft",
    ),
    "restore_catalog": (
        "恢复目录快照",
        "restore catalog snapshot",
        "把 ERP 来源的目录恢复到第 3 版快照",
        "Restore the ERP source catalog to snapshot version 3",
    ),
    "update_metric": (
        "修改指标定义",
        "update metric",
        "把毛利率指标的口径改成含税收入",
        "Change the gross margin metric to use revenue including tax",
    ),
    "rollback_metric": (
        "回滚指标",
        "roll back metric",
        "把出货额指标回滚到第 2 版",
        "Roll the shipment value metric back to version 2",
    ),
    "update_term": (
        "修改业务术语",
        "update glossary term",
        "把「活跃客户」术语的定义改成近 30 天下过单",
        "Define the active customer term as ordered in the last 30 days",
    ),
    "rollback_term": (
        "回滚业务术语",
        "roll back glossary term",
        "把「活跃客户」术语恢复到上一版",
        "Restore the active customer term to its previous revision",
    ),
    "publish_release": (
        "发布数据集版本",
        "publish release",
        "把这个版本发布成 v1.2.0",
        "Release this version as v1.2.0",
    ),
    "import_standards": (
        "导入数据标准",
        "import standards",
        "导入这份字段标准和代码表",
        "Import these field standards and code lists",
    ),
    "update_standard": (
        "修改字段标准",
        "update field standard",
        "把客户编号字段标准的长度改成 20",
        "Change the customer ID field standard length to 20",
    ),
    "update_code_list": (
        "修改代码表",
        "update code list",
        "在车辆类型代码表里加上「工程车」",
        "Add construction vehicle to the vehicle type code list",
    ),
    "confirm_standard_mapping": (
        "确认标准映射",
        "confirm standard mapping",
        "确认订单表的 cust_no 列对应客户编号标准",
        "Confirm the orders cust_no column maps to the customer ID standard",
    ),
    "rollback_standards": (
        "回滚数据标准",
        "roll back standards",
        "把数据标准回滚到第 2 次修订",
        "Roll the standards back to revision 2",
    ),
    "run_kg_extraction": (
        "抽取知识图谱",
        "run knowledge graph extraction",
        "从这个版本的文档里抽一份知识图谱",
        "Extract a knowledge graph from the documents in this version",
    ),
    "create_quality_rule": (
        "创建质量规则",
        "create quality rule",
        "给订单表加一条金额不能为负的质量规则",
        "Add a quality rule that order amounts must not be negative",
    ),
    "update_quality_rule": (
        "修改质量规则",
        "update quality rule",
        "把空值率规则的阈值改成 5%",
        "Change the null rate rule threshold to 5%",
    ),
    "delete_quality_rule": (
        "删除质量规则",
        "delete quality rule",
        "把这条过时的唯一性规则删掉",
        "Delete this outdated uniqueness rule",
    ),
    "run_quality_rule": (
        "运行质量规则",
        "run quality rule",
        "现在跑一下订单金额非负这条规则",
        "Run the non-negative order amount rule now",
    ),
    "change_quality_issue": (
        "认领或解决质量问题",
        "claim or resolve quality issue",
        "这个质量问题我来认领",
        "Mark this quality issue as resolved",
    ),
    "generate_datasheet": (
        "生成数据说明书",
        "generate datasheet",
        "给这个版本生成一份中文数据说明书",
        "Generate an English datasheet for this version",
    ),
    "publish_datasheet": (
        "发布数据说明书",
        "publish datasheet",
        "发布刚检查过的这份数据说明书",
        "Publish the datasheet I just reviewed",
    ),
    "draft_label_set": (
        "起草标签集和标注指南",
        "draft label set and guidelines",
        "按这批图起草一份车辆标签和标注指南",
        "Draft vehicle labels and annotation guidelines from these images",
    ),
}
