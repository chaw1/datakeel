import type { askReasonEn } from "./askReasonEn";

/** 拒答和追问的原因，按服务端记录的原因代码组织措辞。 */
export const askReasonZh: Record<keyof typeof askReasonEn, string> = {
  askWhyAmbiguousMetric: "问题对应多个指标。请选择需要的指标口径。",
  askWhyUnresolvedMetric: "指标引用的目录对象尚未解析。无法执行问数。",
  askWhyTimeUnparsed: "无法可靠解析时间条件: {notes}",
  askWhyGenericMetric:
    "问题只提到泛称, 对应多个可能的指标。请选择需要的指标口径。",
  askWhyNoMetric: "无法用已登记指标回答。以下是最接近的指标。",
  askWhySelectedMetricMissing: "选定指标不存在。请选择已登记指标。",
  askWhySelectedMetricUnresolved: "选定指标或问题条件尚未解析。无法执行问数。",
  askWhyExecutionFailed: "已登记指标暂时无法执行 ({notes})。",
  askWhyTimeNotUnderstood: "无法可靠解析时间条件: 未理解{fragments}",
  askWhyUnsupportedCalculation: "登记指标不支持所问的计算: {fragments}",
  askWhyUnclearCondition: "请明确维度条件: {details}",
  askWhyNotUnderstood: "未理解{fragment}",
  askWhyShareNeedsGrouping: "结果行占比需要明确分组维度或时间粒度。",
  askWhyComparisonPeriodMismatch:
    "指定的对比周期与当前完整时间区间不一致。请明确月份或季度。",
  askWhyYearOverYearNeedsRange: "请明确同比的时间范围。",
  askWhyPreviousPeriodNeedsRange: "请明确环比的时间范围。",
  askWhySamePeriodNeedsRange: "请明确同期对应的有界时间区间。",
  askWhyFollowupTimeUnparsed: "追问的时间条件不可用: {notes}",
  askWhyFollowupMetricUnavailable: "上一轮指标在当前登记口径下不可用。",
  askWhyFollowupDimensionsUnclear:
    "新指标无法明确沿用上一轮维度,请明确筛选和分组。",
  askWhyFollowupComparisonUnclear:
    "请明确需要的对比方式和时间分组,不支持否定或相互冲突的修改。",
  askWhyFollowupChangeUnclear:
    "无法确定追问的修改内容,请明确指标、时间、维度取值或分组。",
  knowledgeWhyPending: "有 {count} 条文档说法的关联待确认。",
  knowledgeWhyMissingCatalog:
    "{name} 在目录里, 但系统和文档都没有登记本题所需的记录。",
  knowledgeWhyMissingGraph:
    "{name} 已解析为图谱实体, 但系统和文档都没有登记本题所需的记录。",
  knowledgeWhySubject: "主语",
  askProfileWhyNoProfile: "没有已发布的时序剖析元数据。",
  askProfileWhyUnknownSubject: "所选数据集没有当前剖析记录。",
  askProfileWhyUnknownColumn: "当前剖析未登记所问的温度列。",
  askProfileWhyAmbiguousDataset: "有多个数据集, 请选择本题的数据集。",
  askProfileWhyIncompleteProfile: "当前版本的断档剖析不完整, 无法可靠排名。",
  askProfileWhyNoRecordedGaps: "当前版本未记录可供排名的设备断档区间。",
  askProfileRankedGapCount:
    "按已发布版本的采样时间轴断档区间数排序; 仅比较有已记录断档的设备。同表中的温度列不代表温度独有的缺值。",
  askProfileRankedDuration:
    "按已发布版本的采样时间轴断档总时长排序; 仅比较有已记录断档的设备。同表中的温度列不代表温度独有的缺值。",
  askChartCaption: "{name}：{rows} 行结果；{columns}",
};
