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


@lru_cache(maxsize=1)
def _prompt_tokens() -> int:
    return estimate_tokens(TRANSCRIBE_PROMPT)


def input_token_bound(width: int, height: int) -> int:
    """Estimate oriented image tokens plus the complete versioned transcription instruction."""
    return ceil(width * height / 1024 + 2) + _prompt_tokens()
