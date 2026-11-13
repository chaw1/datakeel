# 界面设计「校样 · 出处档案」

> 2026-10-23。界面使用校样与出处档案的结构，默认色板为「红蓝双铅笔」；「墨水与赭石」「石墨与钴」作为备选。色板通过同一组 CSS token 切换，具体实现与对比度检查随代码维护。

## 1. 一句话

界面像一份带批注的校样：证据锚点是铅笔批注，每个数字带脚注指回来源，审批卡是一张签批单。datakeel 的每条结论都能回到证据，界面围绕这条阅读路径组织。

## 2. 色板 ②「红蓝双铅笔」（校对室）

象牙白纸，蓝铅笔标出处，朱砂红只管驳回和删除。每个 token 给浅色 / 深色两个值。

| token | 含义 | 浅色 | 深色 |
|---|---|---|---|
| `--paper` | 页面底 | `#F7F5EE` | `#171716` |
| `--sheet` | 版面 / 卡片 / 表格底 | `#FFFEFA` | `#201F1D` |
| `--ink` | 正文墨 | `#1B1D22` | `#ECE8DF` |
| `--muted` | 次要文字 | `#5F5C55` | `#A29D92` |
| `--rule` | 线 / 边框 | `#D9D4C7` | `#3A3731` |
| `--pencil` | 强调：锚点、脚注编号、链接、当前项 | `#2459A8` | `#8CB1EC` |
| `--pencil-wash` | 强调底：锚点底色、选中行 | `#E2E9F4` | `#22304A` |
| `--red` | 红笔：删除、驳回、不可逆、错误 | `#C4321A` | `#F48469` |
| `--ok` | 成功 / 已采纳 | `#536A1C` | `#AFC473` |
| `--warn` | 警示 / 过期将至 | `#8C5800` | `#E5B35A` |

规则：
- 红色只出现在删除、驳回、不可逆和错误上，不做普通强调。
- 强调色只有一个（`--pencil`）。类型色（表 / 字段 / 指标 / 术语）只用在类型标签和图节点上，从 `--ink` 与 `--muted` 的灰阶加一个小色点区分，不另加整套彩色。
- 对比度：正文墨对纸 ≥ 7:1；`--muted`、`--pencil`、`--red`、`--ok`、`--warn` 对纸与对版面均 ≥ 4.5:1；浅深两套都要过。上面的值已自检通过，改值要重算。

备选色板的完整 token 值见 `web/src/styles/palette-ochre.css` 与 `web/src/styles/palette-pencil.css`，字段一一对应。

## 3. 字体

- 标题与大数字：衬线。拉丁用 Source Serif 4（自托管，OFL），汉字回落系统宋体（`"Songti SC", "Noto Serif CJK SC", "SimSun", serif`）。**只用在 18px 及以上**；表格与正文一律黑体。
- 正文：系统黑体栈，拉丁在前、中文在后：`-apple-system, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif`，13px；中文不小于 12px。
- ID、谓词、哈希、SQL：Source Code Pro（自托管，OFL），回落 `SFMono-Regular, Consolas, monospace`。
- 不从 Google Fonts 等外部地址加载字体；demo 离线必须能跑。字体文件只打包用到的字重（衬线 600/700，等宽 400/500），拉丁子集即可。
- 不用 630 这类字重；苹方只有 400/500/600。

## 4. 排版与密度

- 密度 token 三个：行高（正文 1.6，表格 1.45）、间距单位 4px、字号阶（12 / 13 / 14 / 16 / 18 / 24 / 32）。
- 中英混排：字距和大写只给拉丁字母；中英之间用 `text-autospace`（支持的浏览器）；日期写 `10-23 00:24`，不写 `Oct 23, 12:24 AM`；表格数字用等宽数字（`font-variant-numeric: tabular-nums`）。
- 英文标签比中文长 1.5–2 倍，按钮和表头按英文留宽；路径从中间省略保住文件名；中文不在词中间截断。
- 页眉固定写当前对象和版本，像校样的页眉。

## 5. 四个签名组件

1. **三态标记**：`有`（测到，墨字）、`无`（测过没有，墨字加实线方框）、`?`（存疑，铅笔圈出的问号）、`·`（没有这条断言，淡点）。四者互不混淆，不只靠颜色。
2. **证据锚点**：文本中的锚点用铅笔色下划线 + 上标编号；断言矩阵行首写同样的编号；悬停某条断言时文本锚点和图上的框一起描边。
3. **来源脚注**：同一个抽取器 / 来源版本整页只写一次，放在表尾脚注（a、b、c…）；脚注可点，跳到来源对象页或在侧栏展开原始事件。问数页的答案数字带上标，脚注指向指标卡、SQL 和用到的字段。
4. **签批单**：审批卡做成表单式签批单：计划编号、动作与来源对话、影响面、外发、可逆性（不可逆用红笔框住）、计划摘要、有效期（剩余时间）、受影响对象清单、签批人、退回 / 签批按钮、一句"签批只对这份摘要有效"。

另：**图节点**做成档案卡：衬线写名称、等宽写类型和关键数；UUID 不上图；中心节点加投影，其余邻居折叠成「另有 N 个」。

## 6. 和风格无关、必须一起做的 IA 改动

- 导航 13 项平铺改成 6 组：工作台（待审批、运行中、质量告警）/ 数据（数据库、数据目录、问数）/ 证据与质量（证据、质量）/ 操作（审批【带计数】、运行记录）/ 智能体（对话、Trace 与成本）/ 模型（本体）。血缘移进对象页的「关系」tab；报告变成数据集页的 tab；流水线运行 + 动作记录合并为「运行记录」按类型筛。
- 对象页统一模板：头部（类型、名称、短 ID 可复制、状态、主操作）/ 事实条（每个数字可点，跳到产生它的事件）/ 关系（局部图 2 跳 ≤25 节点 + 按边类型分组的列表）/ 证据（按谓词分组，未知与候选在前）/ 历史（只追加事件流）。数据集、文件、版本、动作运行、表、字段、指标、术语共用。
- 证据页：行高从约 272px 压到约 104px（1440×900 同屏 6–7 行）；断言改「概念 × 谓词」矩阵；置信度 1.0 不显示；来源版本全页相同就放进表头；默认把未知多、候选多的样本排前面；「还有 7 条」改成「5 条候选待审」；详情加键盘 j/k/a/r。
- 空态三种说清楚（真没数据 / 筛选清空了 / 抽取器没跑）；问数的澄清态只问一个问题、选项上写口径版本负责人；不可答态说卡在哪并给最近的替代；答不了也记进 Trace。
- ⌘K 快捷搜索：找对象、跳过去、发起对话；不直接执行动作；中文输入法组字时回车不触发；四期起也搜指标和术语。
- 页面标题改成页名加计数，去掉口号式文案。

## 7. 设计系统原语、导航壳层与多色板切换（Design System v2）

- **结构性设计令牌（[tokens.css](../../web/src/styles/tokens.css)）**：在已有字体与字号阶梯基础上补充圆角（`--radius-xs` 至 `--radius-pill`）、控件高度（`--control-sm/md/lg`）、边框线（`--border-subtle/default/strong`、`--surface-hover`、`--rule-strong`）、浮层阴影（`--shadow-sm/md/lg`）、层级（`--z-header` 至 `--z-toast`）及统一缓动与时长（`--ease-standard`、`--duration-fast/normal`），保留高密度扁平纸面排版与单一红/蓝铅笔强调色约束。
- **三套已过审校样色板运行时切换（[PaletteControl.tsx](../../web/src/app/PaletteControl.tsx)）**：保留 `铅笔红蓝`（`pencil`）为未加作用域的默认 `:root` 色板，`赭石钢蓝`（`ochre`）与 `石墨暗红`（`graphite`）分别作用域于 `[data-palette="ochre"]` / `[data-palette="graphite"]`（含亮/暗色与系统偏好），经 `web/scripts/check-contrast.mjs` 自动校验正文/次要/图标与反色对比度；选择状态持久化于 `localStorage["datakeel.palette"]`，可在顶栏即时切换。
- **36 个语义图标集（[Icon.tsx](../../web/src/components/Icon.tsx)）**：在原有 18 个图标基础上新增 `workbench`、`annotation`、`catalog`、`asset`、`standards`、`ask`、`evidence`、`kg`、`rules`、`operator`、`workflow`、`agent`、`memory`、`trace`、`ontology`、`palette`、`sidebar`、`user`，实现全 19 个侧边栏导航项、壳层控件与操作页的一一对应，消除重复占位图标。
- **零依赖校样 UI 原语（`web/src/components/ui/` + [ui.css](../../web/src/styles/ui.css)）**：提供 `Button`（`secondary`/`primary`/`danger`/`ghost`/`link`）、`Select`、`Input`、`Badge`（`neutral`/`accent`/`ok`/`warn`/`danger`/`stamp`）、`Surface`（`sheet`/`paper`/`ledger`）、`PageHeader`、`SegmentedTabs` 与 `EmptyState`，保证原生控件 `:where(...)` 基线重置、`button` 字号始终保持正文无衬线字体（`< 18px`）且不引入外部 UI 组件库或样式传参泄露。
- **可折叠分组侧边栏与 `48px` 紧凑顶栏（[Sidebar.tsx](../../web/src/app/Sidebar.tsx)、[useSidebarState.ts](../../web/src/app/useSidebarState.ts)）**：默认全展开保持既有导航可达性，支持顶栏按钮或 `⌘B` / `Ctrl+B` 折叠为 `64px` 图标窄栏、按分组折叠并持久记忆至 `localStorage`，路由跳转至已折叠分组时自动展开所属分组；`.topbar` 固定吸顶且压缩至 `48px`。
- **多级可点击面包屑与服务端身份徽章（[Breadcrumbs.tsx](../../web/src/app/Breadcrumbs.tsx)、[ActorBadge.tsx](../../web/src/app/ActorBadge.tsx)）**：面包屑展示工作区、导航分组/对象父级（数据库/数据目录/数据标准/运行记录）、对象类型、当前页及对象页签，`runs?type=...` 与对象详情可点击逐级回退；顶栏身份徽章由 `GET /api/production/workbench` 验证服务端 `actor` 与有效权限（`本地模式` / `管理员` / `{N} 项权限` / `只读`）。

## 8. 全局上下文副驾与动作链续规划（Copilot & Chain Replan）

- **全局右侧副驾抽屉（[CopilotDrawer.tsx](../../web/src/features/copilot/CopilotDrawer.tsx)、[copilot.css](../../web/src/styles/copilot.css)）**：通过顶栏按钮或 `⌘J` / `Ctrl+J` 在任意页面唤起 `420px` 校样侧栏（移动端全宽），保留 `⌘K` / `Ctrl+K` 给快速搜索、`⌘B` / `Ctrl+B` 给侧边栏折叠；从搜索结果页脚也可直接将对象提示转入副驾。
- **实时视图上下文与懒加载会话（[pageContext.ts](../../web/src/features/copilot/pageContext.ts)、[useCopilotSession.ts](../../web/src/features/copilot/useCopilotSession.ts)、[CopilotContextBar.tsx](../../web/src/features/copilot/CopilotContextBar.tsx)）**：依据当前路由与所选对象实时推导 `PageContext` 芯片并支持一键暂停/恢复附带；侧栏关闭时不发起任何网络请求，打开时也不预建空会话，仅在首次发送消息时创建会话并透传上下文。
- **动作链续规划与失败重规划（[ChainReplanBar.tsx](../../web/src/features/agent/ChainReplanBar.tsx)、`POST /api/intents/chains/{id}/replan`、`datakeel intents replan`）**：对存在状态依赖延迟步骤（`deferred_steps`）的已完成动作链提供「规划剩余步骤」，对失败动作链提供「按当前状态重新规划」（复用已完成步骤输出 `$ref` 并在实时数据库上重估选择器），始终先生成未执行的 `planned` 新动作链供人工确认。
