# 策略周报页（weekly-report）设计

日期：2026-10-12
状态：已实现

## 0. 背景与定位

在既有「版本策略全景(New)」（`/weekly-new`，浅色 Element Plus 默认风）之外，新增一级菜单「策略周报」（`/weekly-report`）：**同一份 weekly 数据源、同一套业务功能与交互**的看板重塑版——**浅色、与系统样式一致**（Element Plus 默认设计语言），补齐 KPI、分支负载、时段趋势、热点标签四类数据可视化。

硬约束（来自需求）：

- **只改前端页面与布局**：不动任何后端代码、接口调用与数据结构；不新增接口（可视化全部由 weekly 返回数据前端聚合）。
- **保留原有页面全部业务功能与交互**：周导航/月周下拉/版本与分支筛选/统计图例/时间点归行网格/构建与推送芯片/过期置灰只读/编辑弹窗（admin、绑定版本 pm）/借用弹窗（无权限角色）/只读详情弹窗（过期任务）。
- **组件可复用拆分、样式集中管理、避免重复代码**。

## 1. 关键决策

| 决策点     | 结论                                                                                                                                                                                                                                                                             |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 数据逻辑   | 抽取 `src/composables/useWeeklyPanorama.ts`（weekly-new 与 weekly-report 共用）；weekly-new/index.vue 重构为消费该 composable（行为不变，顺带修复月周下拉 `this` 回退失效的隐患），页面只保留展示与弹窗接线                                                                      |
| 弹窗复用   | 直接 import `weekly-new/components/` 三个业务弹窗（编辑/借用/只读详情），样式随系统默认，零逻辑复制                                                                                                                                                                              |
| 派生可视化 | 新增纯函数 `src/utils/weeklyReport.ts`（KPI/分支负载/24h 趋势/标签云），全部单测锁定                                                                                                                                                                                             |
| 主题实现   | `views/weekly-report/theme.scss` 集中管理：`--wk-*` 语义令牌全部映射 Element Plus 变量（`--el-*`），面板对齐 el-card（4px 圆角/白底/浅边框/shadow="never"），徽标/按钮对齐 el-tag/el-button 默认观感；组件 scoped 样式只写差异化部分。**配色与系统保持一致，不引入独立配色体系** |
| 动效       | CSS keyframes（面板错峰淡入、进度条/柱体生长、刷新图标旋转）；`prefers-reduced-motion` 全局降级；无发光、无渐变文字、无暗色画布                                                                                                                                                  |
| 响应式     | ≥1200px：KPI 四列 + 可视化三列；768–1200px：KPI 两列 + 可视化两列（标签云通栏）；<768px：全部单列、工具栏分组换行、网格横向滚动（min-width 760px）                                                                                                                               |

## 2. 页面结构

```
┌───────────────────────────────────────────────────────────────────────┐
│ 页头：徽标 + 标题「策略周报」+ 版本·周期·更新时间 │ 本周进度 4/7 天    │
│      （主色淡底徽标 / 深色标题）                │ 格点 ○●●●○○○ + 角色徽标 + 刷新 │
├───────────────────────────────────────────────────────────────────────┤
│ KPI 磁贴 ×4：策略任务 / 构建任务 / 推送任务 / 今日待执行（含迷你进度条）│
│      图标 chip 走 EP 语义色板（primary/success/warning/danger 淡底）  │
├───────────────────────────────────────────────────────────────────────┤
│ 工具栏面板：◀ ▶ 周范围 第N周 [本周] [月周▾] │ [版本▾] [分支▾] │ 统计 图例│
├───────────────────────────────────────────────────────────────────────┤
│ 调度全景面板（flex 撑满视口，多内容时仅面板内滚动）                     │
│   表头：时间 │ 周一(10.12) … 周日(10.18)（今天列主色淡底 + 今天 tag）   │
│   行 = 有任务的时间点；芯片：构建=分支色实底白字 / 推送=虚线描边透明底   │
│   过期=置灰删除线（仅可查看）；hover 统一降透明度；行错峰淡入            │
├───────────────────────────────────────────────────────────────────────┤
│ 分支负载（堆叠进度条：构建实心+推送斜纹段） │ 时段趋势（24h 堆叠柱      │
│                                              +「现在」success 虚线） │ 热点标签云│
└───────────────────────────────────────────────────────────────────────┘
```

空态三态与原文一致（暂无数据 / 该版本暂无分支 / 所选分支暂无策略），改为 EP 风格虚线框徽标空态。

## 3. 文件清单

新增：

- `frontend/src/views/weekly-report/index.vue` — 页面装配（composable + 派生数据 + 弹窗接线）
- `frontend/src/views/weekly-report/theme.scss` — 集中样式（EP 语义令牌 / 共享面板与徽标类 / 动效）
- `frontend/src/views/weekly-report/components/` — `ReportHeader.vue`（周进度）、`KpiTiles.vue`、`WeekToolbar.vue`、`TechHourGrid.vue`（调度网格）、`GridEmptyState.vue`、`BranchLoadPanel.vue`、`HourTrendPanel.vue`、`TagCloudPanel.vue`
- `frontend/src/composables/useWeeklyPanorama.ts` — 共享数据 composable（含 `HourTaskItem`/`WeekCell`/`TaskClickResult` 类型）
- `frontend/src/utils/weeklyReport.ts` — 派生聚合纯函数
- 测试：`utils/__tests__/weeklyReport.spec.ts`、`composables/__tests__/useWeeklyPanorama.spec.ts`

修改：

- `frontend/src/views/weekly-new/index.vue` — 重构消费 composable（模板与视觉不变；修复月周下拉清空回退失效）
- `frontend/src/views/weekly-new/components/HourGrid.vue` — 类型改为从 composable 导入（单一来源）
- `frontend/src/router/asyncRoutes.ts` — 新增 `/weekly-report`（rank 6），其后菜单 rank 顺延 7~15
- `frontend/src/views/welcome/index.vue` — 新增「策略周报」入口卡片

## 4. 测试与验收

- `npm run test`：新增 19 例（weeklyReport 10 / composable 9），全量通过
- `npm run typecheck` / `lint:eslint` / `lint:prettier` / `lint:stylelint` / `npm run build` 通过
- 视觉验收：dev server + Playwright 截图核对桌面（1440）/平板（834）/移动（390）三档布局；配色与系统（pure-admin 浅色 + EP 默认）一致

## 修订记录（2026-10-15 第四轮质量优化）

- **ReportHeader 周日边界（R4-F4，修 F-M1）**：周进度 7 格点「今天」呼吸圈判定与 `elapsed` 解耦——原条件要求 `elapsed<7`，今天恰为所展示周的周日时 `elapsed=7`，当天 7 格全实心、无 today 标记（R3-F11 修复引入的边界回归）；改为 `todayIndex = diff(today, weekStart)`（0-6，今天落在所展示周内才标记），「整周已过去」（今天在周后，todayIndex=-1）仍不标今天，R3-F11 语义保留。新增组件级边界 spec `components/__tests__/ReportHeader.spec.ts`（今天=周日/今天=周一/历史周/未来周）。
