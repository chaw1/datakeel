# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned structural transcription instruction shared by both VLM protocols."""

from functools import lru_cache
from math import ceil

from datakeel.core.context_tokens import estimate_tokens

# Preserve the measured prompt verbatim, including its original punctuation.
TRANSCRIBE_PROMPT = (
    "把这张图片里的全部文字和结构完整转写出来\uff0c不要总结\uff0c不要遗漏\uff0c不要翻译。\n"
    "规则\uff1a\n"
    "1. 普通段落\uff1a逐字照抄原文\uff0c保持原来的语言。\n"
    "2. 箭头或连线\uff1a每条单独一行\uff0c写成 `A --标签--> B`"
    "\uff08没有标签就写 `A --> B`\uff09\uff0c"
    "A 是箭头起点\uff0cB 是箭头指向的一端。\n"
    "3. 如果箭头是虚线、带叉号\uff0c或者节点是灰色、虚线框\uff0c"
    "在该行末尾用括号注明\uff0c例如\uff08虚线\uff09\uff08灰色\uff09\uff08带叉号\uff09。\n"
    "4. 树状或层级结构\uff1a用缩进列表表示上下级\uff0c每个框里的文字都要写全。\n"
    "5. 表格\uff1a写成 markdown 表格\uff1b有删除线的单元格写成 ~~文字~~\uff0c"
    "灰色的行在行尾注明\uff08灰色\uff09。\n"
    "6. 标题、图例、注释\uff1a照抄。\n"
    "只输出转写结果。"
)
COORDINATE_PROMPT = TRANSCRIBE_PROMPT.removesuffix("只输出转写结果。") + (
    '\n只输出 JSON\uff0c格式为 {"lines":[{"text":"逐行转写内容",'
    '"bbox":[x1,y1,x2,y2]}]}\uff0c不要输出 markdown 代码围栏。'
    "bbox 必须是按 EXIF 方向校正后的原图像素坐标\uff0c左上角为原点\uff0c"
    "x 向右、y 向下\uff0c且 x2>x1、y2>y1\uff1b每行框住该行全部文字或关系涉及的节点。"
    "不能确定位置时省略 bbox\uff0c不得猜测或编造坐标。按原文顺序逐行返回\uff0c"
    "所有结构、箭头方向、删除线和灰色标记都必须保留在 text 中。"
)


def transcription_prompt(version: str, width: int = 0, height: int = 0) -> str:
    """Select additive coordinate instructions without changing legacy recording semantics."""
    if version != "image-transcription-v2":
        return TRANSCRIBE_PROMPT
    dimensions = f"\nCorrected image size: {width} x {height} pixels."
    return COORDINATE_PROMPT + dimensions if width and height else COORDINATE_PROMPT


@lru_cache(maxsize=128)
def _prompt_tokens(version: str, width: int, height: int) -> int:
    return estimate_tokens(transcription_prompt(version, width, height))


def input_token_bound(
    width: int, height: int, prompt_version: str = "image-transcription-v1"
) -> int:
    """Estimate oriented image tokens plus the complete versioned transcription instruction."""
    return ceil(width * height / 1024 + 2) + _prompt_tokens(prompt_version, width, height)
