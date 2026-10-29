# 界面整体优化：视觉一致性与样式统一（2026-10-11）

## 背景与目标

对前端业务页面做整体 UI 优化，聚焦：视觉一致性、布局排版、间距留白、色彩对比与文字层级、控件状态（悬停/选中/焦点）、响应式适配。原则：优先复用项目已有设计规范（Element Plus 语义变量 + pure-admin 基座），不引入新样式体系。

## 现状问题评估

| # | 问题 | 影响 |
|---|------|------|
| 1 | 卡片/筛选栏/统计卡样式在 12+ 页面重复手写，参数漂移（padding 12/16px 混用、边框色 #e5e7eb 与 #ebeef5 混用） | 改一处漏一处，视觉不齐 |
| 2 | 文字/边框/背景色硬编码（#303133/#909399/#c0c4cc/#e5e7eb/#fff/#f5f7fa） | 基座暗色模式下业务页面全部失效（白底刺眼） |
| 3 | 悬停反馈不统一：welcome 卡片用阴影、panorama 卡片用描边变色、weekly 色块用透明度 | 交互语言混乱 |
| 4 | 可点击卡片无键盘焦点态（focus-visible） | 可访问性缺口 |
| 5 | 统计卡片固定 4 列无断点；welcome 页叠加了布局已提供的 24px 外边距 | 窄屏挤压/首屏双重留白 |

## 实施方案

### 1. 新增全局业务样式层 `src/style/business.scss`（唯一新增样式来源）

- 语义变量：`--biz-card-border`（映射 `--el-border-color-lighter`）、`--biz-card-radius`
- 通用类（`biz-` 前缀避免与基座/页面类冲突）：
  - `.biz-page` 页面纵向容器（gap 12px）
  - `.biz-card` 通用卡片（EP 背景/描边/圆角，padding 16px）
  - `.biz-filter-bar` / `.biz-filter-left` 筛选栏（左右分布、窄屏自动换行）
  - `.biz-card-head` / `.biz-card-title` 卡片头与标题
  - `.biz-sub`（13px 次要文案）/ `.biz-tip`（12px 弱化文案）
  - `.biz-stat-grid` 统计网格（4 列 → ≤1200px 2 列 → ≤640px 1 列）
  - `.biz-clickable` 可点击卡片统一悬停/选中/键盘焦点态（0.2s 过渡 + focus-visible 外框）
- 已在 `src/style/index.scss` 注册（`@use "business"`），随全局暗色变量自动适配。

### 2. 颜色语义化映射（全部业务页面）

| 原硬编码 | 替换为 |
|---|---|
| `#303133` 主文字 | `var(--el-text-color-primary)` |
| `#606266` 常规文字 | `var(--el-text-color-regular)` |
| `#909399` 次要文字 | `var(--el-text-color-secondary)` |
| `#c0c4cc` / `#a0a4ab` 占位 | `var(--el-text-color-placeholder)` |
| `#e5e7eb` / `#ebeef5` 边框 | `var(--el-border-color-lighter)` / `-extra-light` |
| `#fff`（容器背景） | `var(--el-bg-color)` |
| `#f5f7fa` / `#fafafa` / `#f0f0f0` | `var(--el-fill-color-light)` / `var(--el-fill-color)` |
| `#ef4444` / `#10b981` / `#e6a23c` | `var(--el-color-danger/success/warning)` 系 |
| `#f0f9eb` / `#fef0f0` / `#fdf6ec` 结论底色 | `var(--el-color-*-light-9)` |
| `#3b82f6` 品牌蓝（徽章/标题强调） | `var(--el-color-primary)` 系 |

**保留的业务语义色**：阶段色板 `STAGE_COLORS`（构建/冒烟/分析/推送）、分支配色 `useBranchColors`、模板颜色调色板、甘特库 theme 配置、色块上的白色文字、报告导出截图的白色背景参数（`html2canvas` 需要）——末项转历史记录：验证报告页已随 2026-10-20 页面精简删除，`html2canvas-pro` 依赖亦于 R7-F11 卸载（其余各项现行有效）。

### 3. 逐页改造清单（16 个文件）

- welcome：入口卡片复用 `.biz-card` + `.biz-clickable`，移除双重外边距
- plan：筛选栏/详情面板复用全局类，图例文字语义化
- strategy：上下两区复用 `.biz-card`，冲突提示改 EP danger 色
- report/index + detail：容器语义化；报告单结论高亮/图标色改 EP 语义色
- execution：统计卡接入响应式 `.biz-stat-grid`
- panorama：策略卡片接入 `.biz-clickable`（悬停+焦点态统一），版本徽章改 EP primary 系
- versionView / logs / weekly：容器与网格线颜色语义化
- weekly-new / slot-booking / slot-config：本已使用 el-card + EP 变量，抽查无需改动
- admin（含 Tab 组件） / branch-config（含启动配置表单）：容器/文字语义化
- components/gantt/GanttGanttastic.vue：外层容器语义化（库内 theme 色板保留）

## 验证结果

| 检查项 | 命令 | 结果 |
|---|---|---|
| 单元测试 | `npm run test`（vitest） | ✅ 7 文件 46/46 通过 |
| 类型检查 | `npm run typecheck` | ✅ 通过 |
| 生产构建 | `npm run build` | ✅ 通过（产物 2.79 MB），dist 已清理 |

## 兼容性与回归风险

1. **暗色模式**：业务页面颜色全部跟随 EP 变量后，开启暗色主题不再出现白底卡片；甘特库 theme 色板仍为浅色固定值，暗色下甘特轨道区仍是浅色（现状遗留，库限制，风险低）。
2. **类名调整**：部分页面模板 class 由 `section`/`filter-bar` 换为 `biz-*`，均为页面内部 scoped 类，无测试断言依赖，回归风险低。
3. **边框/底色微调**：`#e5e7eb → var(--el-border-color-lighter) (#e4e7ed)` 视觉差异 <1 个灰阶，肉眼几乎不可辨。
4. **welcome 首屏留白**：移除了与布局 `.main-content` 重复的 24px padding，首屏内容整体上移，属预期修正。
5. **不受影响**：路由、接口、权限逻辑零改动；所有 diff 均为模板 class 与样式块。
