# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Replayed model sentences for one generated dataset, written with and without fact labels.

Every "good" sentence is true of the facts it cites. LABELLED follows the label, unit and display
wording now given to the model; UNLABELLED restates the same facts in free paraphrase, as a model
that saw only raw field names would. BAD sentences are fabrications that must always be removed.
Facts are built without declared kinds so the same cases also run against older validators.
"""

from datetime import UTC, datetime

from pydantic import JsonValue

from datakeel.core.datasheet_models import DatasheetFact

_FACTS: tuple[tuple[str, str, str, JsonValue], ...] = (
    ("name", "composition", "dataset.name", "Field notes · generated demo"),
    (
        "description",
        "motivation",
        "metadata.description",
        "200 generated images and 200 generated text observations.",
    ),
    ("files", "composition", "manifest.file_count", 398),
    ("modalities", "composition", "manifest.modalities", {"image": 200, "text": 198}),
    ("bytes", "composition", "manifest.total_bytes", 4815739),
    ("quality", "composition", "quality.total", 100.0),
    ("grade", "composition", "quality.grade", "excellent"),
    ("relations", "composition", "kg.relation_count", 54),
    ("created", "collection", "version.created_at", "2026-10-27T15:55:01.562095+00:00"),
    ("operator", "preprocessing", "lineage.operator", "file.dedup"),
    ("state", "preprocessing", "lineage.run_state", "COMPLETED"),
    ("assertions", "preprocessing", "assertions.count", 8158),
    ("license", "distribution", "metadata.license", "https://spdx.org/licenses/Apache-2.0.html"),
    ("creator", "maintenance", "metadata.creator", "Datakeel sample generator"),
    ("owner", "maintenance", "metadata.owner", "张三"),
    ("compliance", "maintenance", "compliance.total", 99.92),
    (
        "issues",
        "maintenance",
        "compliance.issues",
        [
            {
                "dimension": "naming",
                "severity": "warning",
                "message": "naming compliance is 99.75/100",
            }
        ],
    ),
)
FACTS = tuple(
    DatasheetFact(
        id=f"fact-{key}",
        chapter=chapter,  # type: ignore[arg-type]  # Literal chapters are listed above.
        source_type="version",
        source_id="version-1",
        field=field,
        value=value,
        recorded_at=datetime(2026, 10, 27, 15, 55, 1, tzinfo=UTC),
    )
    for key, chapter, field, value in _FACTS
)

# (chapter, text, cited fact keys)
Case = tuple[str, str, tuple[str, ...]]

LABELLED: tuple[Case, ...] = (
    (
        "motivation",
        "数据集描述\uff1a200 generated images and 200 generated text observations。",
        ("description",),
    ),
    ("composition", "数据集名称为 Field notes · generated demo。", ("name",)),
    ("composition", "文件数量为398个。", ("files",)),
    ("composition", "该数据集共有398个文件。", ("files",)),
    ("composition", "数据模态为 image 200个、text 198个。", ("modalities",)),
    ("composition", "总字节数为4,815,739字节。", ("bytes",)),
    ("composition", "质量总分为100.0分。", ("quality",)),
    ("composition", "质量等级为 excellent。", ("grade",)),
    ("composition", "图谱关系数量为54条。", ("relations",)),
    ("collection", "版本创建时间为2026-10-27T15:55:01.562095+00:00。", ("created",)),
    ("collection", "该版本创建于2026年10月27日。", ("created",)),
    ("collection", "版本创建于2026年10月。", ("created",)),
    ("collection", "版本创建时间为2026年10月27日15:55。", ("created",)),
    ("preprocessing", "处理算子为 file.dedup\uff0c处理状态为 COMPLETED。", ("operator", "state")),
    ("preprocessing", "证据断言数量为8,158条。", ("assertions",)),
    ("distribution", "许可为 https://spdx.org/licenses/Apache-2.0.html。", ("license",)),
    ("maintenance", "创建人为 Datakeel sample generator。", ("creator",)),
    ("maintenance", "负责人为张三\uff08名称\uff09。", ("owner",)),
    ("maintenance", "合规总分为99.92分。", ("compliance",)),
    ("maintenance", "合规问题\uff1anaming compliance is 99.75/100。", ("issues",)),
    ("composition", "The dataset name is Field notes · generated demo.", ("name",)),
    ("composition", "The file count is 398 files.", ("files",)),
    ("composition", "The data modalities are image: 200 and text: 198.", ("modalities",)),
    ("composition", "Total bytes: 4,815,739 bytes.", ("bytes",)),
    ("composition", "The quality score is 100.0 points.", ("quality",)),
    ("composition", "The quality grade is excellent.", ("grade",)),
    ("composition", "The graph relation count is 54 relations.", ("relations",)),
    ("collection", "The version creation time is 2026-10-27T15:55:01.562095+00:00.", ("created",)),
    ("collection", "The version creation time is 2026-10-27 15:55.", ("created",)),
    (
        "preprocessing",
        "The processing operator file.dedup has processing state COMPLETED.",
        ("operator", "state"),
    ),
    ("preprocessing", "The evidence assertion count is 8,158.", ("assertions",)),
    ("distribution", "The license is https://spdx.org/licenses/Apache-2.0.html.", ("license",)),
    ("maintenance", "The creator is Datakeel sample generator.", ("creator",)),
    ("maintenance", "The owner is 张三.", ("owner",)),
    ("maintenance", "The compliance score is 99.92 points.", ("compliance",)),
)

UNLABELLED: tuple[Case, ...] = (
    ("motivation", "该数据集收录了200张生成图像和200条生成文本观测。", ("description",)),
    ("composition", "数据集文件总数为398。", ("files",)),
    ("composition", "数据集共包含两种模态。", ("modalities",)),
    ("composition", "数据集体积为4815739字节。", ("bytes",)),
    ("composition", "质量评分为满分100.0。", ("quality",)),
    ("composition", "数据质量评级为优秀。", ("grade",)),
    ("composition", "知识图谱中有54个关系。", ("relations",)),
    ("collection", "该版本于2026年10月27日15:55生成。", ("created",)),
    ("preprocessing", "去重操作 file.dedup 已经成功完成。", ("operator", "state")),
    ("preprocessing", "共标注8158条证据。", ("assertions",)),
    ("distribution", "数据集采用 Apache-2.0 许可证发布。", ("license",)),
    ("maintenance", "数据集由 Datakeel sample generator 自动生成。", ("creator",)),
    ("maintenance", "张三是数据集的维护者。", ("owner",)),
    ("maintenance", "合规得分为99.92。", ("compliance",)),
    ("composition", "The dataset holds 398 files in total.", ("files",)),
    ("composition", "Its size is about 4.6 MB.", ("bytes",)),
    ("composition", "The data quality rating is a perfect 100.", ("quality",)),
    ("maintenance", "Naming compliance stands at 99.75%.", ("issues",)),
)

# (chapter, text, cited fact keys, expected reason)
BadCase = tuple[str, str, tuple[str, ...], str]

BAD: tuple[BadCase, ...] = (
    ("composition", "文件数量为398%。", ("files",), "unsupported_number"),
    ("composition", "该数据集共有4,815,739个文件。", ("bytes",), "unsupported_number"),
    ("composition", "总字节数为398字节。", ("files", "bytes"), "unsupported_number"),
    ("composition", "质量总分为100.0%。", ("quality",), "unsupported_number"),
    ("maintenance", "合规总分为99.92%。", ("compliance",), "unsupported_number"),
    (
        "maintenance",
        "合规问题\uff1anaming compliance is 99.75%。",
        ("issues",),
        "unsupported_number",
    ),
    ("composition", "The dataset contains 4,815,739 files.", ("bytes",), "unsupported_number"),
    ("composition", "The file count is 398 bytes.", ("files",), "unsupported_number"),
    ("composition", "The quality score is 100.0%.", ("quality",), "unsupported_number"),
    ("composition", "该数据集共有399个文件。", ("files",), "unsupported_number"),
    ("composition", "总字节数约为4.6 MB。", ("bytes",), "unsupported_number"),
    ("composition", "数据模态共2种。", ("modalities",), "unsupported_number"),
    ("maintenance", "负责人为李四。", ("owner",), "unsupported_term"),
    ("maintenance", "负责人为李四\uff08名称\uff09。", ("owner",), "unsupported_term"),
    ("maintenance", "Northwind Labs maintains the dataset.", ("creator",), "unsupported_term"),
    ("collection", "该版本创建于2027年1月2日。", ("created",), "unsupported_date"),
    ("collection", "版本创建时间为2026年10月27日16:55。", ("created",), "unsupported_number"),
    ("composition", "文件数量为398个。", ("invented",), "unknown_fact"),
    ("composition", "文件数量为398个。", (), "missing_citation"),
    ("maintenance", "文件数量为398个。", ("files",), "wrong_chapter"),
)
