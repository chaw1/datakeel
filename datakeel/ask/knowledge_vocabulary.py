# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep bilingual catalog types, dependency roles and flow vocabulary in one place."""

from typing import Literal

from datakeel.core.knowledge_models import KnowledgeFocus

CatalogTarget = Literal["table", "view", "metric", "data", "person", "team"]


def _english(pattern: str) -> str:
    return rf"(?<![a-z0-9_])(?:{pattern})(?![a-z0-9_])"


TYPE_WORDS: tuple[tuple[CatalogTarget, str], ...] = (
    (
        "view",
        r"视图|汇总(?:表)?|报表|看板|摘要|"
        + _english(r"views?|summar(?:y|ies)|reports?|dashboards?"),
    ),
    ("table", r"(?:底|源|基础|原始|数据)?表(?!达|示)|" + _english(r"tables?")),
    ("metric", r"指标|" + _english(r"metrics?")),
    (
        "team",
        r"团队|部门|小组|(?<!分)组|" + _english(r"teams?|groups?|departments?|organizations?"),
    ),
    (
        "person",
        r"负责人|责任人|所有者|同事|人员|人|" + _english(r"people|persons?|owners?|colleagues?"),
    ),
    ("data", r"数据|" + _english(r"data|datasets?")),
)
FOCUS_KINDS: dict[CatalogTarget, KnowledgeFocus] = {
    "table": "table",
    "view": "table",
    "data": "table",
    "metric": "metric",
    "person": "person",
    "team": "person",
}
ASSET_LEVELS = {"table": 0, "data": 0, "view": 1, "metric": 2}
ZH_QUANTITY = r"(?:[一二两三四五六七八九十百零\d]+|几)?"
EN_FILL = (
    r"(?:(?:is|are)\s+)?(?:the\s+)?"
    r"(?:(?:one|two|three|four|five|six|seven|eight|nine|ten|several|few|all|\d+)\s+)?"
)
TYPED_QUESTION = (
    rf"(?:哪{ZH_QUANTITY}(?:张|些|个|份|种|项|位|名|组)?|什么)"
    r"(?:(?:排名)?(?:前几|前\d+)|的|\s)*|"
    rf"\b(?:which|what)\s+{EN_FILL}(?:(?:source|underlying|top|ranked)\s+\w*\s*)?"
)
COUNT_QUESTION = r"(?<![前哪])(?:多少|几)(?:个|张|位|名|组|项|份)?\s*|\bhow\s+many\s+"
COUNT_END = (
    r"(?:多少|几)(?:个|张|位|名|组|项|份)(?:呢|呀|啊)?[?\uff1f!。.\s]*$|"
    r"\bhow\s+many(?:\s+(?:are|is)\s+there)?[?!.\s]*$"
)
QUESTION_ANCHOR = r"谁|哪|什么|多少|几|\b(?:who|what|which|how)\b"
TYPE_QUESTION_ANCHOR = (
    r"哪(?:[一二两三四五六七八九十\d]+)?(?:些|个|张|份|种|项|位|名|组)?|什么|\b(?:which|what)\b"
)
COUNT_PREFIX = COUNT_QUESTION + r"|\b(?:the\s+)?(?:number|quantity)\s+of\s+"
COUNT_TOTAL = (
    COUNT_END
    + r"|(?:数量|数目|总数|总共有|一共有|共有|有)\s*(?:是|为)?\s*多少[?\uff1f!。.\s]*$"
    + r"|(?:数量|数目|总数)\s*(?:是|为)?\s*什么[?\uff1f!。.\s]*$"
)
NOUN_FILLER = (
    r"(?:(?:is|are|the|a|an|its|their|all|those|these|of|related|associated|distinct|"
    r"source|base|underlying|registered|available|total|one|two|three|four|five|several|few)\s+)*"
)
NOUN_CLAUSE_BOUNDARY = (
    r"[,\uff0c;\uff1b?!\uff1f]|\b(?:that|which|does|do|did|has|have|is|are|for|from|to|in|on)\b"
)
BUSINESS_COUNT = (
    r"\b(?:orders?|customers?|accounts?|units?|products?|items?|members?)\b|"
    r"订单|客户|件|业务人员|销售额|营业额"
)
BUSINESS_ACTIVITY = r"\b(?:bought|buy|buys|purchased|purchase|purchases|sold|sell|sells)\b"
PREDICATE_AUXILIARIES = (
    r"\s*(?:(?:has|have|had|been|be|is|are|was|were|will|would|can|could|did|do|does|"
    r"recently|already|currently|actually)\s+)*"
)
BUSINESS_HEAD_SUFFIX = r"\s+(?:members?|orders?|customers?|accounts?|units?|rows?|records?)\b"
BUSINESS_QUANTITY = r"业务人员|(?:订单|客户)(?:数量|数目|总数)|(?:多少|几)(?:条|行)\s*(?:数据|记录)"
SCALAR_AGGREGATE = r"总额|合计|\btotal(?:s)?\b"
VALUE_NOUNS = (
    SCALAR_AGGREGATE + "|" + r"指标值|数值|读数|金额|数量|数目|总数|值|"
    r"\b(?:metric\s+values?|values?|amounts?|quantit(?:y|ies)|readings?)\b"
)
VALUE_EN_PREFIX = (
    r"\b(?:what(?:\s+(?:is|are))?|show|display|give\s+me)\s+"
    r"(?:(?:the|a|an|its|their|current|latest|actual|present|numeric|numerical|total|highest|lowest|largest|smallest)\s+)*"
    r"(?:['\u2019]s?\s*)?"
)
AGGREGATE_COMMAND = r"^\s*(?:按[^谁哪什么?\uff1f]*?)?(?:统计|计算|求)\s*(?:合计|总额)"
VALUE_QUESTION = (
    AGGREGATE_COMMAND + "|" + rf"{VALUE_EN_PREFIX}(?:{VALUE_NOUNS})|"
    rf"(?:{VALUE_NOUNS})\s+(?:of\s+)?(?:is|are)\s+what\b|"
    rf"(?:{VALUE_NOUNS})\s*(?:是|为)?\s*(?:什么|多少)|"
    rf"(?:看|查看|显示|展示|给我看看)\s*(?:的)?\s*(?:{VALUE_NOUNS})"
)
VALUE_RELATION_END = r"\b(?:from|on|by|to|for)\s*[?!.]*$"
VALUE_COUNT_NOUNS = SCALAR_AGGREGATE + r"|数量|数目|总数|\bquantit(?:y|ies)\b"
VALUE_READING_WORD = r"\breadings?\b"
VALUE_READING_NOUN = (
    r"\b(?:the|a|current|latest|actual|present|numeric|numerical)\s+readings?\b|"
    r"['\u2019]s?\s+readings?\b|\breadings?\s+of\b|"
    r"\bwhat\s+readings?\s+(?:does|do|did)\b"
)
PERSON_QUESTION = r"谁|哪位|负责人|责任人|所有者|\b(?:who|whose|owner)\b"
LOCATION_QUESTION = r"哪(?:里|儿)|从哪|\bwhere\b"
LIST_COMMAND = r"列出(?:来)?|列一下|列举|列(?:个)?清单|列给|给我看看|\bshow\s+me\b"
NEUTRAL_RELATION = (
    r"相关|有关|关联|对应|挂着|"
    r"\b(?:related|linked|attached|associated|belong(?:s)?\s+underneath)\b"
)
LIST_QUESTION = (
    r"(?<!为)什么|哪些|哪几个|哪(?:个|张|份|种|项)|怎么|如何|"
    r"\b(?:what|everything|list|which|how)\b|" + LIST_COMMAND
)
SUBJECT_SUFFIX = (
    r"\s*[`'\"”』]?\s*(?:(?:这|那|该)(?:张|个)?)?"
    r"(?:数据表|表|视图|指标|\b(?:table|view|metric)\b)"
)
SUBJECT_PREFIX = r"(?:数据表|表|视图|指标|\b(?:table|view|metric))\s*[`'\"“『]?\s*$"

# Hierarchy nouns describe the requested side; only cross-level defaults may resolve a
# direction when the sentence itself does not assign an input or result role.
HIERARCHY_UP = r"上游|上一层|前一层|底层|底下|\b(?:upstream|underneath|underlying|beneath)\b"
HIERARCHY_DOWN = r"下游|下一层|后一层|\bdownstream\b"
SOURCE_NOUNS = r"来源|源头|源表|数据源|输入|基础|依据|\b(?:sources?|inputs?|basis|foundation)\b"
FLOW_DESTINATION = (
    r"去向|下一站|流向|流到|流入|送到|供给|提供给|供数|支撑|用于|供(?=谁|哪|什么|多少|几)|"
    r"\b(?:fed\s+into|feeds?|powers?|supports?|supplies|supply|produces?|generates?|sources?\s+for)\b"
)
BARE_USAGE_ZH = r"(?:用|读)(?=\s|[?!.\u3002\uff1f\uff01\uff0c,;\uff1b]|$)"
FLOW_DEPENDENCY = (
    r"依赖|基于|依托|用到|使用|用(?:过|了|着)|用(?=哪|什么|\s)|调用|读取|消费|订阅|引用|"
    r"取自|来自|出自|源于|从|"
    r"\b(?:from|based\s+on|built\s+on|depends?\s+on|uses?|used|using|consumes?|consumed|"
    r"reads?|read|reading|calls?|called|calling|consuming|references?|subscribes?\s+to)\b|"
    + BARE_USAGE_ZH
)
USAGE_ZH = r"使用|用到|用过|用了|用着|引用|读取|消费|依赖|调用|订阅|" + BARE_USAGE_ZH
USAGE_EN_PAST = r"used|consumed|read|referenced|called"
PRODUCTION_EN_PAST = r"fed|powered|supported|supplied|produced|generated"
PRODUCTION_ZH = r"生成|加工|计算|产出|汇总|衍生"
RESULT_NOUNS = r"输出|结果|产物|\b(?:outputs?|results?|products?)\b"
OWNERSHIP = r"负责|维护|分管|管理|归属|\b(?:owns?|owner|maintains?|manages?|responsible)\b"
IMPACT = (
    r"影响|受牵连|牵连|波及|连累|受影响|会让|导致|"
    r"\b(?:affects?|affected|impacts?|impacted|influences?|causes?|breaks?|break|suffers?)\b"
)
IMPACT_PASSIVE = r"\b(?:affected|impacted)\s+by\b|受(?:到)?"
DEPENDENCY_CONSEQUENCE = (
    IMPACT + r"|会坏|无法(?:更新|生成)|不能(?:更新|生成)|失去(?:数据)?(?:来源|输入|供给)|"
    r"\b(?:fail\w*|stop\s+(?:working|refreshing)|lose\w*\s+(?:(?:its|their)\s+)?(?:data\s+)?feed)\b"
)
CONSUMPTION = (
    rf"(?:{USAGE_ZH})|\b(?:uses?|used|using|consumes?|consuming|reads?|reading|"
    r"calls?|calling|depends?\s+on)\b"
)
COUNTERFACTUAL = (
    r"(?:要是|如果|假如|假设|一旦).*?(?:没了|消失|停了|停用|下线|删除|删掉|不可用)|"
    r"\b(?:if|without)\b.*?\b(?:disappear(?:s|ed)?|remove[ds]?|unavailable|stop(?:s|ped)?|"
    r"vanish(?:es|ed)?|fail(?:s|ed)?|missing|gone|deleted|dropped)\b|"
    r"\bwithout\b"
)
CALCULATION_QUESTION = (
    r"怎么算|怎么.*算|如何.*(?:算|计算)|计算公式|公式|"
    r"\bformula\b|\bhow\b.*\b(?:calculat(?:e|es|ed|ing)|comput(?:e|es|ed|ing))\b"
)
PERSON_DEPENDENCY = (
    rf"(?:{CONSUMPTION})|(?:{FLOW_DESTINATION})|(?:{SOURCE_NOUNS})|"
    rf"(?:{PRODUCTION_ZH})|\b(?:{PRODUCTION_EN_PAST})\b"
)
EMPLOYMENT = (
    r"就职|任职|供职|隶属|所属|属于|汇报|"
    r"\b(?:work(?:s|ed|ing)?\s+(?:for|at)|reports?\s+to|belongs?\s+to)\b"
)
WORK_WORDS = r"工作|\bwork\b"
CONDITION_WORDS = r"要是|如果|假如|假设|一旦|若|\bif\b"
ABSENCE_WORDS = (
    r"没了|没有|不存在|消失|停了|停用|停更|停掉|停供|断供|停止更新|"
    r"不再(?:更新|供数|提供数据|可用)|下线|删除|删掉|不可用|"
    r"\b(?:went|go(?:es)?|going|go)\s+away\b|"
    r"\b(?:disappear\w*|remove\w*|unavailable|stop\w*|vanish\w*|missing|gone|deleted|dropped)\b"
)
CAUSAL_INPUT = r"(?:因|由于)\s*§|\b(?:because\s+of|due\s+to)\s+§"
SUPPLEMENTARY_CLAUSES = (r",\s*(?:which|that)\b[^,]*(?:,|$)",)
NOMINAL_APPOSITION = (
    r",\s*(?:the|an?|this|that)\s+(?:upstream|downstream|underlying)\s+"
    r"(?:metric|table|view|report|dashboard|summary)\s*(?=[?!.]*$)"
)
CONCESSIVE_CLAUSE = r"^\s*although\b[^,]+,|^.*?虽然[^,\uff0c]+[,\uff0c]\s*但"
TEMPORAL_CLAUSE = r"\b(?:before|after|while)\s+(?:it|they)\b"
SUBJECT_TYPE_PRONOUN = (
    r"\b(?:this|that)\s+(?:table|view|metric)\b|(?:这|那|该)(?:张|个)?(?:表|视图|指标)"
)
SUBJECT_PRONOUN = r"\b(?:its\s+output|it|its)\b|它|其|" + SUBJECT_TYPE_PRONOUN
TOPIC_WITH_SUBJECT = (
    r"^[^,\uff0c:\uff1a\u2014\u2013]*§[^,\uff0c:\uff1a\u2014\u2013]*"
    r"[,\uff0c:\uff1a\u2014\u2013]\s*"
)
ABSENCE_PREPOSITION = r"\bwithout\b"
SOURCE_PREPOSITIONS = {"from", "从"}

# A marker replaces only the already resolved subject; these are grammatical templates,
# never complete questions or catalog-specific names.
SUBJECT_MARKER = "§"
SOURCE_ROLES = (
    r"§\s+appears?\s+on\b",
    r"(?:看板|报表|视图)\s*(?:会|可|可以|正在)?\s*显示\s*§",
    rf"(?:以|拿|用|把)\s*§\s*(?:拿来|用来)?\s*(?:当(?:作)?|作(?:为)?|为)\s*(?:{SOURCE_NOUNS})",
    rf"§\s*(?:作(?:为)?|充当)\s*(?:{SOURCE_NOUNS})",
    rf"\b(?:use|uses|using|take|takes|taking|treat|treats|treating)\s+§\s+as\s+(?:an?\s+|the\s+)?(?:{SOURCE_NOUNS})",
    rf"§\s+(?:as|serves?\s+as)\s+(?:an?\s+|the\s+)?(?:{SOURCE_NOUNS})",
    rf"§\s+(?:is\s+)?(?:an?\s+|the\s+)?(?:{SOURCE_NOUNS})\s+(?:to|for)\b",
    rf"§\s+as\s+(?:their\s+|its\s+|an?\s+|the\s+)?(?:{SOURCE_NOUNS})",
    rf"§\s*是[^,\uff0c?\uff1f]*?(?:的)\s*(?:{SOURCE_NOUNS})",
    rf"§\s*(?:的|之)\s*(?:{RESULT_NOUNS})",
    r"\b(?:fed\s+by|derived\s+from|built\s+(?:on|from)|pull(?:s|ed|ing)?\s+from)\s+§",
    r"(?:从|来自)\s*§\s*(?:出来|而来)?",
    rf"§\s*(?:当(?:作)?|为)\s*(?:{SOURCE_NOUNS})",
)
RESULT_ROLES = (
    r"(?:给|为)\s*§\s*提供数据",
    rf"§\s*(?:的|之)\s*(?:{SOURCE_NOUNS})",
    rf"(?:{SOURCE_NOUNS})\s+(?:of|for|to)\s+§",
    r"§\s+(?:is\s+|was\s+)?(?:fed\s+by|derived\s+from|built\s+(?:on|from))",
    rf"§\s*(?:是[^,\uff0c?\uff1f]*?的)\s*(?:{RESULT_NOUNS})",
    rf"§\s+(?:is\s+)?(?:an?\s+|the\s+)?(?:{RESULT_NOUNS})\s+(?:of|from)\b",
    rf"§\s+as\s+(?:their\s+|its\s+|an?\s+|the\s+)?(?:{RESULT_NOUNS})",
    r"(?:给|为)\s*§\s*供数",
)

ROLE_CLAUSE = r"[^,;?.!\uff0c\uff1b\uff1f\u3002\uff01]*"
PRODUCTION_FRAME_EN = (
    r"feeds?|fed|supplies|supply|supplied|produces?|produced|"
    r"generates?|generated|builds?|built"
)
INPUT_COMPLEMENT = r"with|using|from"
EN_INPUT_FRAME = (
    rf"\b(?P<verb>{PRODUCTION_FRAME_EN})\b"
    rf"(?P<receiver>{ROLE_CLAUSE}?)\b(?P<prep>{INPUT_COMPLEMENT})\b"
    rf"(?P<input>{ROLE_CLAUSE})"
)
ZH_INPUT_FRAME = (
    rf"(?P<tool>用|拿)(?P<input>{ROLE_CLAUSE}?)"
    rf"(?P<verb>{PRODUCTION_ZH})(?P<result>{ROLE_CLAUSE})"
)
ZH_PASSIVE_SUPPLY = rf"由(?P<supplier>{ROLE_CLAUSE}?)供数"
EN_SUPPLY_TO = (
    rf"\b(?:supplies|supply|supplied)\s+(?:the\s+)?inputs?\s+to\b"
    rf"(?P<receiver>{ROLE_CLAUSE})"
)
PASSIVE_AUXILIARY = r"\b(?:is|are|was|were|been|being)\s*$"
PAST_PRODUCTION = frozenset({"fed", "supplied", "produced", "generated", "built"})
SUBJECT_EXISTENCE = rf"§\s*(?:有|是){ROLE_CLAUSE}?(?:{TYPED_QUESTION}|{COUNT_QUESTION})"
ZH_SUBJECT_PRONOUN = r"它|其"

CLAUSE_DELIMITER = r"[,;?.!\uff0c\uff1b\uff1f\u3002\uff01]"
HIERARCHY_NOUN_GAP = r"[\s的]*"
PREDICATE_LINK = (
    r"\s*(?:(?:is|are|was|were|has|have|had|been|being|will|would|can|could|may|might|"
    r"do|does|did|not|never|also|still|now|[a-z]+ly)\s+)*|"
    r"\s*(?:会|能|可|可以|正在|在|正|曾|曾经|也|还|都|一直|已经|到底|被|由)*\s*"
)
TOPIC_USAGE_ZH = rf"(?:{USAGE_ZH}|用|读)"
ZH_RECIPIENT_USAGE = (
    rf"(?:给|让|供)(?P<consumer>{ROLE_CLAUSE}?)(?:{TOPIC_USAGE_ZH})"
    rf"(?P<resource>{ROLE_CLAUSE})"
)

ZH_TOPIC_USAGE = (
    rf"§\s*[,\uff0c]?\s*(?:目前|现在|还|都|是|有|\s)*"
    rf"(?P<actor>(?:谁|哪|多少|几){ROLE_CLAUSE}?)"
    rf"(?P<usage>{TOPIC_USAGE_ZH})(?P<object>{ROLE_CLAUSE})"
)
ZH_ELIDED_OBJECT = r"\s*(?:了|过|着|呢|啊|呀|它|其)*\s*"

GROUP_QUESTION_HEAD = (
    r"(?:按|每|各)\s*(?:谁|哪|什么|多少|几)|"
    r"\b(?:for|by|per)\s+(?:who|whose|what|which|where|how\s+(?:many|much))\b"
)
METRIC_WHERE_FILTER = (
    rf"{SUBJECT_MARKER}\s+where\s+"
    r"(?!(?:who|whose|what|which|where|it|its|they|their)\b)"
    r"[a-z][a-z0-9_]*(?:\s+[a-z][a-z0-9_]*)?\s*"
    r"(?:!=|<=|>=|=|<|>|\b(?:is|are|equals?)\b)[^?!.\uff1f\u3002\uff01]*"
)

# Restrictive attributes bind to the requested catalog noun, not every later verb.
RELATIVE_ANCHOR_EN = r"\s+(?:that|who|which)\b"
RELATION_PREDICATE = rf"(?:{CONSUMPTION})|(?:{FLOW_DESTINATION})|(?:{OWNERSHIP})"
RELATIVE_MAIN_AUXILIARY = r"\b(?:does|do|did|is|are|was|were|can|could|will|would)\s*$"
RELATIVE_HEAD_END_ZH = r"的\s*$"

RELATIVE_QUESTION_ANCHOR = rf"(?:{TYPE_QUESTION_ANCHOR})|(?:{COUNT_QUESTION})"

QUESTION_PLACEHOLDER = r"(?:ones?|of\s+(?:them|these|those))\b"

STRUCTURAL_TOP = "\\bon\\s+top\\s+of\\b"
SCALAR_REDUCTION = r"\b(?:average|mean|median|sum|minimum|maximum)\b"
METRIC_SCALAR_HEAD = (
    r"^\s*what\s+(?:is|are|was|were)\s+(?:(?:the|a|an)\s+)?"
    rf"(?:(?:{SCALAR_REDUCTION})\s+(?:of\s+)?)?§\s*[?!.]*\s*$"
)
IMPACT_SOURCE_ROLE = (
    "\\b(?:impacts?|effects?)\\s+of\\s+(?:(?:changing|modifying|updating|removing|deleting)\\s+)?§"
)
IMPACT_CONDITION_SOURCE = (
    r"\bif\s+§\s+(?:(?:is|was|were|gets?|got)\s+)?"
    r"(?:changes?|changed|modified|updated)\b|"
    r"(?:要是|如果|假如|假设|一旦|若)\s*§\s*(?:改变|改动|变化|变了|修改)"
)
POSSESSIVE_RELATION_HEAD = (
    rf"\s*['\u2019]s\s+(?:{OWNERSHIP}|{SOURCE_NOUNS}|{CALCULATION_QUESTION})\s*[?!.]*$"
)

PRODUCTION_PURPOSE_EN = (
    rf"\b(?:{USAGE_EN_PAST})\s+(?:to|for|when)\s+"
    r"(?P<production>build(?:ing)?|generat(?:e|ing)|produc(?:e|ing)|comput(?:e|ing)|calculat(?:e|ing))\b\s*"
    rf"(?P<result>{ROLE_CLAUSE})"
)
SOURCE_EVENT_PREFIX = (
    rf"§\s*(?:(?:这个月|本月|这周|本周|今天|现在|不再|已|已经|一旦|若|要是|如果)\s*)*"
    rf"(?:{ABSENCE_WORDS})(?:了)?\s*(?:(?:以后|之后|后|时)\s*|[,\uff0c])"
)

GROUP_QUESTION_CLAUSE = GROUP_QUESTION_HEAD + r"|谁|哪|什么|多少|几"

SCALAR_COMPARISON = (
    r"(?:超过|不足|达到|大于|小于|高于|低于)\s*(?:预算)?\s*[零一二两三四五六七八九十百千万亿\d]|"
    r"比[^,\uff0c?\uff1f]*?(?:增加|下降|增长|减少)|"
    r"\b(?:greater|less|higher|lower)\s+than\s+\d"
)
SCALAR_OUTPUT_COMMAND = (
    r"^\s*(?:把\s*)?§\s*[,\uff0c]?\s*(?:列出|给出|展示|显示)\s*"
    r"(?:各类|各项|各组|分别的)?(?:金额|数值|件数|数量)\s*[?\uff1f!.。]*$"
)
METRIC_QUANTITY_HEAD = r"§\s*[,\uff0c]?\s*(?:有|是)?\s*多少\s*[?\uff1f!.。]*$"

TOPIC_CONDITION_GAP = r"[\s,\uff0c]*"

GROUPED_SCALAR_OUTPUT = r"各(?:类|项|组)\s*(?:数量|金额|数值|件数)\s*"
