# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Normalize multilingual field vocabulary and physical database type names."""

import re
from functools import lru_cache

_WORDS: dict[str, str] = {
    "cust": "customer",
    "client": "customer",
    "clnt": "customer",
    "num": "id",
    "pk": "id",
    "primarykey": "id",
    "number": "id",
    "no": "id",
    "identifier": "id",
    "amt": "amount",
    "qty": "quantity",
    "cnt": "count",
    "dt": "date",
    "tel": "phone",
    "mobile": "phone",
    "telephone": "phone",
    "emailaddress": "email",
    "prod": "product",
    "wh": "warehouse",
    "dept": "department",
    "addr": "address",
    "desc": "description",
    "nm": "name",
    "usr": "user",
    "emp": "employee",
    "cd": "code",
    "stat": "status",
    "sts": "status",
    "prc": "price",
    "created": "create",
    "creation": "create",
    "updated": "update",
    "quantity": "quantity",
    "total": "amount",
    "timestamp": "time",
}
_CHINESE: dict[str, str] = {
    "版本": "version",
    "修订": "revision",
    "租户": "tenant",
    "逻辑删除": "delete",
    "删除": "delete",
    "经度": "longitude",
    "纬度": "latitude",
    "哈希": "hash",
    "校验和": "checksum",
    "调试": "debug",
    "缓存": "cache",
    "客户": "customer",
    "顾客": "customer",
    "用户": "user",
    "商品": "product",
    "产品": "product",
    "订单": "order",
    "门店": "store",
    "仓库": "warehouse",
    "供应商": "supplier",
    "员工": "employee",
    "部门": "department",
    "编号": "id",
    "号": "id",
    "标识": "id",
    "号码": "id",
    "编码": "code",
    "代码": "code",
    "名称": "name",
    "姓名": "name",
    "名字": "name",
    "类型": "type",
    "日期": "date",
    "时间": "time",
    "周期": "cycle",
    "金额": "amount",
    "数量": "quantity",
    "区域": "region",
    "地区": "region",
    "渠道": "channel",
    "类别": "category",
    "分类": "category",
    "状态": "status",
    "单价": "unit price",
    "价格": "price",
    "退款": "refund",
    "实付": "paid",
    "支付": "paid",
    "标价": "list",
    "发货": "shipped",
    "开票": "invoiced",
    "发票": "invoice",
    "账单": "invoice",
    "票据": "invoice",
    "收据": "receipt",
    "小票": "receipt",
    "折扣": "discount",
    "预算": "budget",
    "电话": "phone",
    "手机": "phone",
    "邮箱": "email",
    "邮件": "email",
    "地址": "address",
    "创建": "create",
    "更新": "update",
    "加入": "joined",
}
_CJK = re.compile("|".join(sorted(_CHINESE, key=len, reverse=True)))


_VOCABULARY = tuple(
    sorted(
        set(_WORDS)
        | set(_WORDS.values())
        | {word for value in _CHINESE.values() for word in value.split()},
        key=lambda word: (-len(word), word),
    )
)


def _compact_words(word: str) -> tuple[str, ...]:
    remaining = word
    pieces: list[str] = []
    while remaining:
        prefix = next((item for item in _VOCABULARY if remaining.startswith(item)), None)
        if prefix is None:
            return (word,)
        pieces.append(prefix)
        remaining = remaining[len(prefix) :]
    return tuple(pieces)


@lru_cache(maxsize=4096)
def name_tokens(name: str, *, expand_aliases: bool = True) -> frozenset[str]:
    """Split camel case, abbreviations and Chinese business words into shared tokens."""
    split = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name)
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", split).lower()
    split = re.sub(r"(?<![a-z])primary[\W_]+key(?![a-z])", " id ", split)
    split = _CJK.sub(lambda match: " " + _CHINESE[match[0]] + " ", split)
    words = (
        word
        for match in re.finditer(r"[a-z]+|[\u4e00-\u9fff]+", split)
        for word in _compact_words(match[0])
    )
    identity = {"num", "pk", "primarykey", "number", "no", "identifier", "cd", "nm", "dt"}
    tokens = frozenset(
        _WORDS.get(word, word) if expand_aliases or word in identity else word for word in words
    )
    if "email" in tokens:
        tokens -= {"address"}
    return tokens - {"id"} if "phone" in tokens else tokens


def canonical_type(data_type: str) -> str:
    """Collapse physical SQL aliases without silently coercing text to numbers."""
    name = re.sub(r"\(.*\)", "", data_type).strip().lower()
    aliases = {
        "int": "integer",
        "bigint": "integer",
        "smallint": "integer",
        "int64": "integer",
        "int32": "integer",
        "serial": "integer",
        "bigserial": "integer",
        "varchar": "string",
        "nvarchar": "string",
        "text": "string",
        "char": "string",
        "character varying": "string",
        "character": "string",
        "str": "string",
        "decimal": "number",
        "numeric": "number",
        "float": "number",
        "double": "number",
        "double precision": "number",
        "real": "number",
        "float64": "number",
        "bool": "boolean",
        "datetime": "timestamp",
        "timestamptz": "timestamp",
        "timestamp without time zone": "timestamp",
        "timestamp with time zone": "timestamp",
    }
    return aliases.get(name, name)


def compatible_type(actual: str, expected: str) -> bool:
    """Accept integer storage for numeric standards while preserving other distinctions."""
    left, right = canonical_type(actual), canonical_type(expected)
    return left == right or (left == "integer" and right == "number")
