# 标注工作台

从侧栏打开**标注工作台**（`#/labeling`），原有工作概览继续保留。选择生产项目和任务包：个人档只有**我的数据**，小组档和团队档按服务器有效权限显示**我的任务**、**审核队列**、**项目驾驶舱**。通过现有 production CLI 创建项目、已发布标签集和任务包；`datakeel production demo` 可生成带离线预测的个人框标注项目。

顶部模块栏展示项目、任务包和真实生产进度；操作栏提供保存、撤销、重做、提交和导航；中间是画布或文本；右侧抽屉提供属性、不可变修订历史、审核意见和指南。

## 模板和键盘操作

模板复用现有带版本的 `ProductionTemplate`，标签来自项目关联的已发布标签集版本。没有模板时默认使用框。`annotation_type` 定义主要组件，`component_config` 可配置：

```json
{
  "components": ["box", "classification"],
  "label_mode": "multi",
  "shortcuts": {"cat": "1", "dog": "2"},
  "guidelines": "只标注可见物体。"
}
```

首批组件是框、多边形、分类和文本片段。标签名称是用户内容，标注保存稳定标签 ID。项目经理通过模板配置界面调用 `create_label_set` 保存新版本。保留 P29 已有共享模板语义：关联同一模板 ID 的项目使用该模板当前目录版本；抽屉展示模板名称、修订号和标签集版本。

所有控件可通过 Tab 到达。编辑器内按 `?` 打开快捷键表；`Ctrl/⌘+S` 保存，`Ctrl/⌘+Enter` 提交，`Ctrl/⌘+Z` 撤销，`Ctrl/⌘+Shift+Z` 或 `Ctrl/⌘+Y` 重做，`Alt+N`/`Alt+P` 保存后切换任务。文本输入框保留原生文本撤销。

- 框：`B` 添加，方向键移动，Shift+方向键调边，`Ctrl/⌘+D` 复制，Delete 删除。拖画、变换手柄、坐标字段和 JSON 属性都以原图像素坐标为准。
- 多边形：`P` 开始，方向键移动光标，Space 加点，Enter 闭合，Escape 取消。选中点后可修改坐标或按 Shift+方向键移动；剩余点数有效时可用 Backspace 删点。
- 分类：单选或多选控件支持 Tab、Space 和方向键，也支持标签快捷键；`label_mode` 控制单选/多选。
- 文本：鼠标或 Shift+方向键选字后按 Enter，也可填写起止位置；支持嵌套。坐标按原文 Unicode 码点计数，与 Python 一致，保留 emoji 和 CRLF 原文位置。

## 自动保存和审核

改动立即保留为本机草稿，500 毫秒防抖后通过 `save_revision` 保存。请求串行化；保存途中产生的新改动会继续补存。草稿按用户、项目、任务隔离；同一标签页的工作区快照帮助刷新后恢复当前任务。恢复草稿须先核验服务器身份才可同步。完全断网刷新时能否加载网页本身取决于浏览器和静态托管缓存，本期未安装 service worker。

预取后两条任务、修订及已解码图片。切换前先补存，离线或冲突会保留当前草稿。撤销历史不设固定步数上限，实际受设备内存/存储限制；未保存草稿可刷新恢复，已完成的撤销时间线保留在当前会话。

409 会显示明确提示：选择**重新加载服务器修订**才放弃本机改动；选择**用我的改动覆盖**会重新读取当前修订，再做比较并交换保存。如果同时发生另一笔写入，仍会再次显示冲突。设备存储失败有警告，恢复联网后自动补存。

个人档提交即通过；小组审核针对确切当前修订通过或填写意见打回，返工保留原标注员。审核队列按返工轮次、模型置信度、预标注差异、稳定任务 ID 排序。差异是精确标签/形状/属性集合的 1−多重集 Jaccard，一致性信号不等于模型准确率。驾驶舱直接展示 P29 进度、人员工作量、置信度分布、标注一致性、以审核通过结果为参考的预标注完全一致率和多轮返工任务，不另存一套数字。定稿先显示冻结的动作计划，再由人单独点击**签批并定稿项目**。

界面隐藏无有效范围的动作，写入仍走已有受控动作和服务端角色、归属校验。样本读取复用项目与源文件授权。零用户实例保留本机个人档行为。

## 无损往返

`AnnotationRecord` 增加可选多边形以及记录、形状和文本片段属性，保留旧字段与接口。定稿后通过受控 `export_dataset`，选择 `annotations_jsonl` 格式；归档中的 `annotations.jsonl` 保存完整核心记录。用已有版本训练集 `import-annotations` 接口传入 `format: "annotations_jsonl"`、`annotations_jsonl` 内容和新的 `idempotency_key` 即可导回。COCO/YOLO 行为不变，检测格式无法表达全部四种组件及属性。

## 画布选型

直接运行时依赖只新增固定版本 Konva **10.9.0** 和 react-konva **19.3.2**，传递闭包及实际打包模块纳入现有许可审计。Konva 是已定选择；以下适配判断是根据上游文档做出的工程推断。

许可来源：[Konva](https://github.com/konvajs/konva/blob/master/LICENSE)、[react-konva](https://github.com/konvajs/react-konva/blob/master/LICENSE)、[Fabric.js](https://github.com/fabricjs/fabric.js/blob/master/LICENSE)、[PixiJS](https://github.com/pixijs/pixijs/blob/dev/LICENSE)。

| 方案 | 上游能力及来源 | 对本工作台的适配判断 |
|---|---|---|
| [Konva](https://konvajs.org/docs/overview.html)、[react-konva](https://github.com/konvajs/react-konva) | Canvas 场景图、命中检测、分层、变换和 React 绑定；MIT | 已选。声明式形状编辑能对接 React 状态和撤销历史，原生 DOM 控件提供键盘可访问性。 |
| [Fabric.js](https://www.fabricjs.com/docs/) | 交互对象画布、控制点、自定义属性及序列化；MIT | 可以承担对象编辑，但独立画布对象状态需要额外维护与 React 的同步。 |
| [PixiJS](https://pixijs.com/8.x/guides/concepts/render-loop) | GPU 场景渲染和连续渲染循环；MIT | 适合密集动态场景，标注控制点、表单和可访问行为需自行补充。 |
| [Canvas2D](https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API) / [SVG](https://www.w3.org/TR/SVG2/) | 浏览器原生栅格绘制 / 向量 DOM | 不新增库，但命中检测、选择、变换及状态同步需要自己维护；SVG 适用于较小的 DOM 图形。 |

Konva 画布按视口尺寸分配；大图提供最长边 1024 像素缩略图，再换成高清原图。缩放平移只变换组，不分配 8000×6000 的画布。这里采用渐进加载，没有实现分块服务；性能须在目标浏览器和硬件实测。

## 可重复验证

生成纯本机样本（含 2000×1500、3840×2160、8000×6000 图片）：

```sh
DATAKEEL_HOME=/tmp/workbench-home uv run python scripts/workbench_fixture.py \
  --output /tmp/workbench-manifest.json --source-dir /tmp/workbench-source
DATAKEEL_HOME=/tmp/workbench-home uv run python scripts/workbench_fixture.py --serve
cd web
npm run smoke:workbench -- http://127.0.0.1:8840 /tmp/workbench-evidence /tmp/workbench-manifest.json
```

脚本使用真实 API 验证 W1–W5：纯键盘标注并提交、离线恢复和显式冲突选择、四种组件各 200 步撤销重做、大图平移五秒，并记录性能数据及浅深色截图。每次全量运行使用新生成的样本。PostgreSQL 使用 `--test-database --schema p30_workbench`，由宿主提供已明确授权的隔离测试库，不能使用归属不明或共享库。Web/API 只使用 8840。

Vitest 覆盖渲染和状态，严格类型、lint、API、token、对比度、源码哈希、构建和许可检查照常执行。沙箱阻止浏览器启动属于未测量，不能记成性能通过。本任务完整两栈门禁和全量变异由集成 CI 执行。
