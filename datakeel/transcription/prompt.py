# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned structural transcription instruction shared by both VLM protocols."""

from functools import lru_cache
from math import ceil

from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.transcription_models import CoordinateSpace
from datakeel.transcription.loader import contracts_path

# The packaged asset preserves the measured instruction byte for byte.
_PROMPT_PATH = contracts_path() / "prompts" / "image-transcription-v1.txt"
TRANSCRIBE_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
COORDINATE_PROMPT = TRANSCRIBE_PROMPT.removesuffix("只输出转写结果。") + (
    '\n只输出 JSON\uff0c格式为 {"lines":[{"text":"逐行转写内容",'
    '"bbox":[x1,y1,x2,y2]}]}\uff0c不要输出 markdown 代码围栏。'
    "bbox 必须是按 EXIF 方向校正后的原图像素坐标\uff0c左上角为原点\uff0c"
    "x 向右、y 向下\uff0c且 x2>x1、y2>y1\uff1b每行框住该行全部文字或关系涉及的节点。"
    "不能确定位置时省略 bbox\uff0c不得猜测或编造坐标。按原文顺序逐行返回\uff0c"
    "所有结构、箭头方向、删除线和灰色标记都必须保留在 text 中。"
)


@lru_cache(maxsize=128)
def transcription_prompt(
    version: str, width: int = 0, height: int = 0, coordinate_space: CoordinateSpace = "pixel"
) -> str:
    """Select additive coordinate instructions without changing legacy recording semantics."""
    if version != "image-transcription-v2":
        return TRANSCRIBE_PROMPT
    prompt = COORDINATE_PROMPT
    if coordinate_space != "pixel":
        maximum = "1000" if coordinate_space == "normalized_1000" else "1"
        prompt = prompt.replace(
            "按 EXIF 方向校正后的原图像素坐标",
            f"按 EXIF 方向校正后的归一化坐标\uff0cx 和 y 均在 0 到 {maximum} 之间"
            f"\uff0c原图右下角为 [{maximum},{maximum}]",
        )
    dimensions = f"\nCorrected image size: {width} x {height} pixels."
    return prompt + dimensions if width and height else prompt


def input_token_bound(
    width: int,
    height: int,
    prompt_version: str = "image-transcription-v1",
    coordinate_space: CoordinateSpace = "pixel",
) -> int:
    """Estimate oriented image tokens plus the complete versioned transcription instruction."""
    return ceil(width * height / 1024 + 2) + estimate_tokens(
        transcription_prompt(prompt_version, width, height, coordinate_space)
    )
