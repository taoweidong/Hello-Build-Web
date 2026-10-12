# 策略周报页（weekly-report）设计

日期：2026-10-12
状态：已实现

## 0. 背景与定位

在既有「版本策略全景(New)」（`/weekly-new`，浅色 Element Plus 默认风）之外，新增一级菜单「策略周报」（`/weekly-report`）：**同一份 weekly 数据源、同一套业务功能与交互**的视觉重塑版——深色科技风看板，补齐 KPI、分支负载、时段趋势、热点标签四类数据可视化。

硬约束（来自需求）：

- **只改前端页面与布局**：不动任何后端代码、接口调用与数据结构；不新增接口（可视化全部由 weekly 返回数据前端聚合）。
- **保留原有页面全部业务功能与交互**：周导航/月周下拉/版本与分支筛选/统计图例/时间点归行网格/构建与推送芯片/过期置灰只读/编辑弹窗（admin、绑定版本 pm）/借用弹窗（无权限角色）/只读详情弹窗（过期任务）。
- **组件可复用拆分、样式集中管理、避免重复代码**。

## 1. 关键决策

| 决策点 | 结论 |
|--------|------|
| 数据逻辑 | 抽取 `src/composables/useWeeklyPanorama.ts`（weekly-new 与 weekly-report 共用）；weekly-new/index.vue 重构为消费该 composable（行为不变，顺带修复月周下拉 `this` 回退失效的隐患），页面只保留展示与弹窗接线 |
| 弹窗复用 | 直接 import `weekly-new/components/` 下三个业务弹窗（编辑/借用/只读详情），父级透传 `class="wk-dialog"` 由集中样式暗色化，零逻辑复制 |
| 派生可视化 | 新增纯函数 `src/utils/weeklyReport.ts`（KPI/分支负载/24h 趋势/标签云）+ `src/utils/color.ts`（hexToRgba），全部单测锁定 |
| 主题实现 | `views/weekly-report/theme.scss` 集中管理：CSS 变量令牌 + `.wk-scope` 页内 Element Plus 深色覆盖 + `body.wk-tech-on` teleport 浮层（下拉/消息/时间面板）覆盖 + `.wk-dialog` 弹窗暗色化；组件 scoped 样式只写差异化部分 |
| 动效 | CSS keyframes（面板错峰淡入、进度条/柱体生长、今天呼吸圈、刷新脉冲）；`prefers-reduced-motion` 全局降级；`backdrop-filter` 仅用于面板与弹窗，不在芯片上滥用 |
| 响应式 | ≥1200px：KPI 四列 + 可视化三列；768–1200px：KPI 两列 + 可视化两列（标签云通栏）；<768px：全部单列、工具栏分组换行、网格横向滚动（min-width 760px） |

## 2. 页面结构

```
┌───────────────────────────────────────────────────────────────────────┐
│ 页头：徽标 + 标题「策略周报」+ 版本·周期·更新时间 │ 本周进度 4/7 天    │
│      （渐变文字）                          │ 格点 ○●●●○○○ + 角色徽标 + 刷新 │
├───────────────────────────────────────────────────────────────────────┤
│ KPI 磁贴 ×4：策略任务 / 构建任务 / 推送任务 / 今日待执行（含迷你进度条）│
├───────────────────────────────────────────────────────────────────────┤
│ 工具栏面板：◀ ▶ 周范围 第N周 [本周] [月周▾] │ [版本▾] [分支▾] │ 统计 图例│
├───────────────────────────────────────────────────────────────────────┤
│ 调度全景面板（flex 撑满视口，多内容时仅面板内滚动）                     │
│   表头：时间 │ 周一(10.12) … 周日(10.18)（今天列青光带+呼吸 pill）      │
│   行 = 有任务的时间点；芯片：构建=分支色渐变实底 / 推送=虚线描边淡底     │
│   过期=置灰删除线；hover 上浮+分支色光晕；行错峰淡入                    │
├───────────────────────────────────────────────────────────────────────┤
│ 分支负载（堆叠进度条：构建实心+推送斜纹段） │ 时段趋势（24h 堆叠柱      │
│                                              +「现在」参考线） │ 热点标签云│
└───────────────────────────────────────────────────────────────────────┘
```

空态三态与原文一致（暂无数据 / 该版本暂无分支 / 所选分支暂无策略），改为自绘发光徽标空态。

## 3. 文件清单

新增：

- `frontend/src/views/weekly-report/index.vue` — 页面装配（composable + 派生数据 + 弹窗接线 + body 浮层类管理）
- `frontend/src/views/weekly-report/theme.scss` — 集中样式（令牌/EP 覆盖/弹窗/动效）
- `frontend/src/views/weekly-report/components/` — `ReportHeader.vue`（周进度）、`KpiTiles.vue`、`WeekToolbar.vue`、`TechHourGrid.vue`（调度网格）、`GridEmptyState.vue`、`BranchLoadPanel.vue`、`HourTrendPanel.vue`、`TagCloudPanel.vue`
- `frontend/src/composables/useWeeklyPanorama.ts` — 共享数据 composable（含 `HourTaskItem`/`WeekCell`/`TaskClickResult` 类型）
- `frontend/src/utils/weeklyReport.ts`、`frontend/src/utils/color.ts` — 派生聚合纯函数
- 测试：`utils/__tests__/color.spec.ts`、`utils/__tests__/weeklyReport.spec.ts`、`composables/__tests__/useWeeklyPanorama.spec.ts`

修改：

- `frontend/src/views/weekly-new/index.vue` — 重构消费 composable（模板与视觉不变；修复月周下拉清空回退失效）
- `frontend/src/views/weekly-new/components/HourGrid.vue` — 类型改为从 composable 导入（单一来源）
- `frontend/src/router/asyncRoutes.ts` — 新增 `/weekly-report`（rank 6），其后菜单 rank 顺延 7~15
- `frontend/src/views/welcome/index.vue` — 新增「策略周报」入口卡片

## 4. 测试与验收

- `npm run test`：新增 21 例（color 7 / weeklyReport 10 / composable 9），全量通过
- `npm run typecheck` / `lint:eslint` / `lint:prettier` / `lint:stylelint` / `npm run build` 通过
- 视觉验收：dev server + Playwright 截图核对桌面（1440）/平板（834）/移动（390）三档布局与弹窗暗色化
