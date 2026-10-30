export const wbTemplateEn = {
  productionUpgradeProjectTemplate: "upgrade project template",
  wbTemplateLock: "Template version",
  wbTemplateLockCurrent: "Current template v{current}, latest v{latest}",
  wbTemplateLockLabels: "Labels v{current}, latest published v{latest}",
  wbTemplateLockUpToDate: "This project uses the newest versions.",
  wbTemplateLockNewer:
    "A newer version exists. This project keeps v{current} until a signed upgrade.",
  wbTemplateUpgrade: "Prepare upgrade",
  wbTemplateUpgradeTitle: "Upgrade this project's template",
  wbTemplateUpgradeSign: "Sign and upgrade",
  wbTemplateUpgradeFrom:
    "Template v{from} → v{to}; labels v{labelsFrom} → v{labelsTo}",
  wbTemplateUpgradeLabels:
    "Labels added: {added}; removed: {removed}; renamed: {renamed}; changed: {changed}",
  wbTemplateUpgradeAttributes:
    "Attributes added: {added}; removed: {removed}; changed: {changed}; newly required: {required}",
  wbTemplateUpgradeSettings: "Other template settings changed: {settings}",
  wbTemplateUpgradeCounts:
    "{tasks} {tasks, plural, one {task switches} other {tasks switch}} versions; {annotated} {annotated, plural, one {has} other {have}} annotations ({objects} {objects, plural, one {object} other {objects}}).",
  wbTemplateUpgradeInvalid:
    "{tasks} existing {tasks, plural, one {annotation} other {annotations}} ({objects} {objects, plural, one {object} other {objects}}) would not pass the new version:",
  wbTemplateUpgradeAllValid:
    "Every existing annotation passes the new version.",
  wbTemplateUpgradeOnly:
    "Only this project changes. Other projects keep their versions.",
  wbTemplateUpgradeNone: "none",
  wbTemplateUpgraded: "Upgraded. This project now uses template v{version}.",
  wbTemplateSavedVersion:
    "Saved as template v{version}. Projects keep their locked version; upgrade each one from its cockpit.",
};
