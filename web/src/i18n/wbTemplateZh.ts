import type { wbTemplateEn } from "./wbTemplateEn";

export const wbTemplateZh: Record<keyof typeof wbTemplateEn, string> = {
  productionUpgradeProjectTemplate: "升级项目模板版本",
  wbTemplateLock: "模板版本",
  wbTemplateLockCurrent: "当前模板 v{current}，最新 v{latest}",
  wbTemplateLockLabels: "标签集 v{current}，最新发布 v{latest}",
  wbTemplateLockUpToDate: "本项目用的已经是最新版本。",
  wbTemplateLockNewer: "有新版本。签批升级之前，本项目继续用 v{current}。",
  wbTemplateUpgrade: "准备升级",
  wbTemplateUpgradeTitle: "升级本项目的模板",
  wbTemplateUpgradeSign: "签批并升级",
  wbTemplateUpgradeFrom:
    "模板 v{from} → v{to}；标签集 v{labelsFrom} → v{labelsTo}",
  wbTemplateUpgradeLabels:
    "标签新增：{added}；删除：{removed}；改名：{renamed}；其它改动：{changed}",
  wbTemplateUpgradeAttributes:
    "属性新增：{added}；删除：{removed}；修改：{changed}；新变成必填：{required}",
  wbTemplateUpgradeSettings: "模板其它设置改动：{settings}",
  wbTemplateUpgradeCounts:
    "{tasks} 条任务切换版本；其中 {annotated} 条有标注（共 {objects} 个标注对象）。",
  wbTemplateUpgradeInvalid:
    "{tasks} 条已有标注（{objects} 个标注对象）在新版本下不合格：",
  wbTemplateUpgradeAllValid: "已有标注在新版本下全部合格。",
  wbTemplateUpgradeOnly: "只有本项目会变，其它项目保持各自的版本。",
  wbTemplateUpgradeNone: "无",
  wbTemplateUpgraded: "已升级，本项目现在用模板 v{version}。",
  wbTemplateSavedVersion:
    "已保存为模板 v{version}。各项目仍用自己锁定的版本，需要的项目请在驾驶舱里升级。",
};
