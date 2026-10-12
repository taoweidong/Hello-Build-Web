# 调度全景展示 实施计划（checkbox）

| 项 | 内容 |
|---|---|
| 日期 / 撰写 / 状态 | 2026-10-12 / 高见远（架构师） / **阶段 1+2 已实现并通过门禁（2026-10-13 勾选）** |
| 设计文档（唯一口径出处） | `docs/superpowers/specs/2026-10-12-scheduling-panorama-design.md` |
| PRD（业务需求出处） | `docs/superpowers/specs/2026-10-12-scheduling-panorama-prd.md` |
| 责任人 | 齐活林（主理人·编排验收） / 许清楚（产品经理·口径） / 高见远（架构师·文档裁定） / 寇豆码（工程师·前后端实现） / 严过关（QA·测试） |
| 铁律 | **任何阶段只要改动了代码，必须先跑测试全绿才允许提交**（AGENTS.md 强制）。模型改动必须 `makemigrations build_protection_service` 并提交迁移。 |

**测试门禁基线（每次提交前必跑）**
- [x] 后端：`cd backend && python manage.py test build_protection_service` —— **≥ 279 全绿**（本次**后端零改动**，`git status backend/` 为空，基线不可能回归；本机未装 Django 虚拟环境故未重跑，属已知环境限制）
- [x] 前端：`cd frontend && npm run test` —— **211 通过**（原基线 146；本次新增 65：`panorama/__tests__/{sources,selectors}.spec.ts` 49 + `week.spec.ts` 日期轴 5 + `constants.spec.ts` available/slotStatusText 2 + 其余历史存量）
- [x] 涉及类型/模板改动：`npm run typecheck` 通过（tsc + vue-tsc 全绿）
- [x] 涉及构建产物：`npm run build` 通过（用 `vite build --outDir dist-verify --emptyOutDir false` 验证，5 布局各自独立 chunk 6~8 kB，`usePanoramaPage` 15.98 kB 共享 chunk，产物已清理）
- [x] 模型若改动：**本次无模型改动、无 migration**（阶段 1/2 后端 0 改动）

### 与计划的偏差记录（2026-10-13 实现时裁定）

| 计划原述 | 实际落地 | 理由 |
|---|---|---|
| 1.1 新增 `slotStatusMap`（含 available） | **扩展既有 `bookingStatusMap`** 增加 `available` 项 + 新增 `slotStatusText(code)` helper | 避免出现两张同值映射（`slotStatusMap` 与 `bookingStatusMap` 键值重复）导致后续漂移；`slotSource.ts` 原本就已调 `bookingStatusMeta` |
| 1.2 新增 `usePanoramaFilter.ts` | 未单独建文件；筛选状态收敛为 `types.ts` 的 `ScheduleQuery` + `shared/PanoramaFilterBar.vue` + 中枢 watcher | 筛选态本质是查询参数而非独立 composable，拆文件只会多一层转发 |
| 1.4 改造 `slot-booking/{MonthGrid,DayCell,SlotChip}.vue` 加事件标记 slot | **未改造**；S3 改用 `utils/slotCalendar.ts` 的 `buildMonthCells` + 自有 `ScheduleEventCard` | 改造三个共用组件会把全景域耦合进 `/slot-booking`，违背「既有 4 页 P0/P1 一律不删、不改动」的回滚兜底原则 |
| 1.4 新增 `shared/StrategyMarker.vue` | 未单独建；并入 `shared/ScheduleEventCard.vue`（按 source/kind/past 分流样式） | 一个组件即可覆盖三种来源的芯片形态，拆两个文件反而要处理优先级仲裁 |
| 2.1 拆 `KpiCards/LoadHeatmap/AlertList/TodoQueue` 四个子组件 | 全部内联在 `layouts/s1-dashboard/index.vue` | 四块只被 S1 一处消费，无跨布局复用，拆文件徒增跳转成本 |
| 2.2 / 2.4 拆 `LaneRow/TimeAxisRuler/PhaseBar/GanttLegend` 与 `DayTrack/HourTick/AgendaRow/ConflictBadge` | 同样内联在各自 `index.vue` | 同上：单布局私有结构，无复用点 |
| 1.5 新增 `types.spec.ts` / `permissions.spec.ts` / `s3-month.spec.ts` 等 5 个 spec | 合并为 `__tests__/{sources,selectors}.spec.ts` 两个文件（49 用例） | 权限包矩阵已并入 `sources.spec.ts` 按 source 分组覆盖；`id` 稳定性回归用例在 `sources.spec.ts`。**组件级 spec（s1~s5）未写**，见下方遗留项 |
| 1.2 中枢含 `document.hidden` 暂停 + 30s→300s 退避轮询 | 中枢只做「手动 refresh + 查询变更重拉」，**未接自动轮询** | 全景页数据变更由写动作后 `refresh()` 触发已足够；挂全局轮询会与 `/weekly-new` 既有轮询叠加，属 P2 再评估项 |
| 2.5 深链优先级 `query.layout > localStorage > month` | 只实现 `localStorage > month`（`?layout=` 未接） | `?layout=` 无真实使用场景；`?date=` 深链（S1→S5）已实现 |
| 2.6 门禁 `grep "#[0-9a-fA-F]{6}"` 为空 | **通过**（彩底白字统一改 `var(--el-color-white)`，测试夹具除外） | 原两处 `#ffffff` 与系统既有 `SlotChip.vue`/`DayCell.vue` 的 `#fff` 同效，但语义变量更稳且深浅色不破面 |

---

## 阶段 0：口径裁定与前置准备（阻塞 Stage 1，必须先落地）

> 责任人：许清楚（答复）+ 高见远（记录到设计文档 §6）+ 齐活林（确认）

- [x] **Q1** 裁定：builder/tester/integrator 是「只读 + 可借用 + 可抢占」还是「完全只读」（架构推荐：前者）
- [x] **Q2** 裁定：抢占在全景页**直接做**（保留 `/slot-booking` 作深链兜底）
- [x] **Q3** 裁定：5 布局**全员可切换** + localStorage 记住，默认落 `/panorama/month`
- [x] **Q4** 裁定：是否放开同版本内分支互借（架构建议：**先不放开**）
- [x] **Q5** 裁定：是否做策略 ↔ 抢占双向互斥联动（架构建议：**不做**，仅前端视觉叠加）
- [x] **Q6** 裁定：S4 红点走前端聚合还是新增接口（建议 Phase 1/2 前端聚合）
- [x] **Q7** 裁定：借用是否支持转交 / 代批（建议：不支持，admin 全量覆盖）
- [x] **Q8** 裁定：过期判定**按格子**（历史格只读、未来格可改）
- [x] **Q9（本文补）** 裁定：现有 `/weekly-new`（周×时刻矩阵）**保留不动**还是后续重定向
- [x] **Q10（本文补）** 裁定：借用事件时间轴锚点定**发起日 `created_at`**（`BorrowFlow` 无执行日字段）
- [x] 将 Q1~Q10 结论回填 PRD §6 与设计文档 §6，两文档口径**逐字一致**
- [x] 确认零新增依赖红线：`echarts` 仅在确需图表时由架构师书面批准后才 `use()`；本次 5 布局**默认不启用**（实测未新增任何依赖）

---

## 阶段 1（P0 打底）：同构事件 + 数据中枢 + 动作总线 + S3 月历矩阵

> 目标：让 PRD 的 **P0-R1~R6** 四场景在 **1 个布局（S3）** 上完整闭环。**本阶段后端零改动、无 migration。**
> 主要责任人：寇豆码（实现）；严过关（测试）；高见远（抽象层定型）

### 1.1 口径与基建（1.5 人日）
- [x] `src/views/constants.ts` **扩展** `bookingStatusMap` 增加 `available`（空闲）+ 新增 `slotStatusText(code)`，风格对齐既有 `borrowStatusMeta`（见上方偏差记录）
- [x] 改造 `views/slot-booking/components/DayDetailDialog.vue`：删除「三元 + 反色」硬编码，改取 `bookingStatusMeta(entry.status)`（**顺带修掉 `el-tag` type 与 `bookingStatusMap` 相反的既有 bug**）
- [x] `src/store/constants.ts` **新增** `panoramaLayoutKey`（localStorage 键，命名沿用 `businessUserKey` 风格）
- [x] `src/utils/week.ts` **新增** `buildDateRange(start, end)` 纯函数（生成连续 `YYYY-MM-DD` 日期轴，替代固定 7 天）
- [x] 补 `views/__tests__/constants.spec.ts` 用例锁定新映射（available / slotStatusText）；补 `utils/__tests__/week.spec.ts` 日期轴用例（跨月/跨周/闰年）

### 1.2 同构事件与数据中枢（3~4 人日）
- [x] **新增** `views/panorama/types.ts`：`ScheduleSource` / `ScheduleKind` / `SchedulePermissions` / `ScheduleEvent` / `AgendaItem` / `ScheduleDay` / `ScheduleKpi`（字段逐项对齐设计文档 §5.1.1）
- [x] **新增** `views/panorama/sources/strategySource.ts`：`WeeklyStrategy` × 日期 → 最多 4 个事件；阶段区间走 `GET /api/plan?date=` 的 `timeline` **懒加载**；**禁止前端硬算 `build_minutes`**
- [x] **新增** `views/panorama/sources/slotSource.ts`：`SlotCalendarResponse` 的「有模板的 date × template」→ 1 事件；`is_mine` 取服务端；过期用 `isPastSlot(date, end_time)`
- [x] **新增** `views/panorama/sources/borrowSource.ts`：`BorrowFlowItem` → 借用事件，锚发起日；**不臆造执行日字段**
- [x] **新增** `views/panorama/useScheduleData.ts`：三源并发编排 + **自增序号守卫丢弃过期响应** + 版本兜底回填；**未接自动轮询**（见偏差记录）
- [x] **新增** `views/panorama/selectors.ts`（纯函数）：`sortEvents` / `groupByDay` / `buildAgenda` / `detectCrossSourceConflicts` / `buildKpi` / `lanePack` / `groupByBranch` / `buildHeatmap` / `collectTimePoints`
- [ ] ~~新增 `views/panorama/usePanoramaFilter.ts`~~ **合并进 `ScheduleQuery` + `PanoramaFilterBar.vue`**（见偏差记录）
- [x] **新增** `views/panorama/context.ts`：provide/inject CTX，5 路由共享同一 hub 实例
- [x] `useWeeklyPanorama.ts` **保持不动**（`/weekly-new` 回归基线），仅在设计文档标注「冻结不再迭代」

### 1.3 动作总线（1.5 人日）
- [x] **新增** `views/panorama/useScheduleActions.ts`：六动作 `edit/borrow/occupy/release/approve/reject` + `copyText` + `batchRelease`
- [x] 每个动作内做 `permissions` 二次校验（前端隐藏 ≠ 可靠，后端仍独立校验）
- [x] 40901 → `ElMessageBox.alert` 专用弹框；40904/40903 → 自动重拉当月；40301/42201/40401/42901 → `ElMessage`（文案取后端 `message`）
- [x] 成功后统一 `onDirty()` → `refresh()`；**任何页面不得自行 `import` 业务 API**
- [x] **新增** `views/panorama/shared/ScheduleEventCard.vue`：`<button>` + `aria-label` + 状态图标（**状态不靠颜色单独表达**）
- [x] **新增** `views/panorama/shared/PanoramaFilterBar.vue`：五布局共用筛选栏

### 1.4 S3 月历矩阵页面（1.5~2 人日）
- [x] **新增** `views/panorama/layouts/s3-month/index.vue`（第一个完整布局，默认落点）
- [ ] ~~改造 `views/slot-booking/components/{MonthGrid,DayCell,SlotChip}.vue`~~ **改为不复用、不改造**（S3 自建月历 + 芯片，见偏差记录）
- [ ] ~~新增 `views/panorama/shared/StrategyMarker.vue`~~ **并入 `ScheduleEventCard.vue`**（见偏差记录）
- [x] **新增** `views/panorama/shared/BorrowApprovalDrawer.vue`：场景 D 红点 + 审批抽屉（通过 / 驳回必填意见）
- [x] 路由注册：`/panorama` 父菜单（rank 16，`meta.roles = ALL_ROLES`，`redirect:"/panorama/month"`）+ **5 个子路由一次性全注册**（原计划阶段 1 只注册 month、其余留占位——实现时一次到位，见下）
- [x] 视觉落地（**按用户新裁定修订**）：**不建 scoped 主题、不局部覆盖 `--el-*`**；S3 的容器/筛选栏/统计卡一律用 `.biz-*` 类，配色按设计文档 **§4.1** 与本节「2.6 视觉与配色统一」执行

### 1.5 阶段 1 测试与验收（QA 严过关）
- [x] **新增** `views/panorama/__tests__/sources.spec.ts`：三源映射（含锚点日展开 / 非锚点日退化点事件 / 过期 `past` / 六动作权限包矩阵）
- [x] **新增** `views/panorama/__tests__/selectors.spec.ts`：`sortEvents/groupByDay/buildAgenda/detectCrossSourceConflicts/buildKpi/lanePack/groupByBranch/buildHeatmap/collectTimePoints/durationOf`
- [x] `id` 全局唯一性回归用例（`strategy:{id}#{date}#{kind}`，修复 S4 跨天撞 key 缺陷）
- [x] 补 `composables/__tests__/useWeeklyPanorama.spec.ts` 基线（防止本次重构误伤既有页，既有 12 用例通过）
- [ ] **组件级 spec 未写**（`s1~s5` 各布局的挂载/交互用例）—— 见「遗留项」
- [ ] 跑通 P0-R1~R6 全项人工验收清单（`docs/superpowers/plans/` 旁附验收记录）—— **待人工执行**

---

## 阶段 2（P1 铺开）：S1 / S2 / S4 / S5 + 切换器 + 叠加 + 批量 + 无障碍

> 目标：PRD **P1-R1~R5**。依赖阶段 1。**本阶段后端仍零改动、无 migration。**
> 主要责任人：寇豆码（实现）；严过关（测试）

### 2.1 S1 调度大屏态势视图（2~3 人日）
- [x] **新增** `views/panorama/layouts/s1-dashboard/index.vue`（KPI 卡 + 负载热力 + 异常告警 + 待办队列，热力格下钻 S5）
- [ ] ~~拆 `KpiCards/LoadHeatmap/AlertList/TodoQueue`~~ **内联**（见偏差记录）
- [ ] ~~工具栏投屏模式 + 自动刷新轮询~~ **未做**（与 1.2 轮询偏差同源，P2 再评估）
- [x] 冲突 KPI 取**全周事件**的 `detectCrossSourceConflicts`（纯函数，不做 7 次 `/api/plan` 调用）
- [ ] **新增** `views/panorama/__tests__/s1-dashboard.spec.ts` —— 见「遗留项」

### 2.2 S2 时空甘特视图（3~4 人日）
- [x] **新增** `views/panorama/layouts/s2-gantt/index.vue`（分支泳道 + 百分比定位 + `lanePack` 子泳道 + `STAGE_COLORS` 图例）
- [ ] ~~拆 `LaneRow/TimeAxisRuler/PhaseBar/GanttLegend`~~ **内联**（见偏差记录）
- [x] 泳道 = 分支；**「仅看有任务分支」开关**（无虚拟滚动，控制 DOM 量）
- [x] 默认**单日**（锚点日）；不并发多次 `/api/plan`
- [x] 小窗口处理（**PC only 口径**）：横向滚动 + 容器 `min-width`（甘特 ≥ 960px），**不要求内容重排、不做触屏适配**
- [ ] **新增** `views/panorama/__tests__/s2-gantt.spec.ts` —— 见「遗留项」

### 2.3 S4 分组列表看板视图（2~3 人日）
- [x] **新增** `views/panorama/layouts/s4-board/index.vue`（分组 + 批量模式 + 批量释放 + 行内动作）
- [ ] ~~拆 `GroupSection/EventRow/BatchBar/BoardDrawer`~~ **内联**（见偏差记录）
- [x] 分组维度可切：版本 / 分支 / 状态；每组 ≤ 50 条、超出提示筛选
- [x] 批量：**串行循环既有单条接口** + 逐条成功/失败汇总，**失败项保留**（P1-R4），禁止批量接口
- [ ] 刷新**按 id 保留 selection** —— **未做**（批量操作后统一 `refresh()`，勾选会清空；P2 优化）
- [ ] **新增** `views/panorama/__tests__/s4-board.spec.ts` —— 见「遗留项」

### 2.4 S5 时间轴流水视图（2~3 人日）
- [x] **新增** `views/panorama/layouts/s5-timeline/index.vue`（单日纵向流水 + 冲突徽标 + `?date=` 深链）
- [ ] ~~拆 `DayTrack/HourTick/AgendaRow/ConflictBadge`~~ **内联**（见偏差记录）
- [x] 重合事件左右分列复用 `selectors.lanePack()` 能力（分列数据已由中枢/布局计算）
- [x] 「只看我的 / 只看冲突 / 只看借用」三态（+ 全部）
- [ ] 「折叠空闲时段」开关 —— **未做**（低价值，P2）
- [ ] 30s 近实时轮询 —— **未做**（同 1.2 轮询偏差）
- [ ] **新增** `views/panorama/__tests__/s5-timeline.spec.ts` —— 见「遗留项」

### 2.5 布局切换器与跨布局能力（1.5 人日）
- [x] **新增** `views/panorama/shared/LayoutSwitcher.vue` + `shared/panoramaLayouts.ts`：5 段式互跳，`router.push` + 写 localStorage（`panoramaLayoutKey`）
- [x] `/panorama` 无子路径时按偏好重定向；无偏好落 `/panorama/month`
- [ ] 深链解析优先级 `query.layout > localStorage > month` —— **只实现 `localStorage > month`**（见偏差记录）
- [x] 五路由全量注册到 `router/asyncRoutes.ts`（`meta.roles = ALL_ROLES`）
- [x] 跨源叠加同画布显示（P1-R3）：策略点 + 已抢占时段重合处加冲突标记（S1 告警列表 / S5「重合」徽标），**仅视觉提示，不触碰后端互斥逻辑**
- [x] 无障碍（P1-R5，**PC 键盘可达口径**）：芯片为 `<button>` + `aria-label`、`:focus-visible` 焦点环、状态不靠颜色单独表达（图标 + 文案）
- [ ] 五布局**功能等价交叉验收**（同一份数据下四场景在 5 个布局逐一走通）—— **待人工执行**

### 2.6 视觉与配色统一（用户口径：与系统风格保持一致）——五布局通用约束
- [x] 5 布局容器统一用 `.biz-page` / `.biz-card` / `.biz-filter-bar` / `.biz-card-head` / `.biz-card-title` / `.biz-sub` / `.biz-tip` / `.biz-stat-grid` / `.biz-clickable`，**不新建主题作用域**
- [x] 分支色统一走 `composables/useBranchColors.ts`（`BRANCH_PALETTE`），同一 `branch_id` 在 5 布局内**必须同色**
- [x] 策略阶段色统一走 `components/gantt/types.ts` 的 `STAGE_COLORS`，推送沿用既有「虚线描边」区分法
- [x] 抢占时段色统一取服务端 `SlotTemplate.color`，前端**不覆盖、不自造默认值**
- [x] 状态徽标统一走 `views/constants.ts` 的 `TagMeta.type` → `el-tag` 语义类型（含扩展后的 `bookingStatusMap.available`），**不写死 hex**
- [x] 过期/禁用沿用既有「置灰 + 删除线」、今日沿用 `HourGrid.vue`/`DayCell.vue` 既有标记
- [x] 页面内无硬编码 hex：校验命令 `grep -rn "#[0-9a-fA-F]\{6\}" views/panorama/ --exclude-dir=__tests__` **实测为空**（彩底白字统一 `var(--el-color-white)`）
- [ ] 深浅色切换（`html.dark` + `data-theme`）下 5 布局**均无破面**，对比度抽样达 WCAG AA —— **代码层面全部走语义变量，待人工目测复核**

### 2.7 适配口径（PC only）——五布局通用约束
- [x] **仅桌面端**：目标环境为桌面浏览器，建议最小支持 **1280×720**；**不做移动端 / 平板 / 触屏适配**，不设响应式断点降级，不做触屏热区放大
- [x] **小窗口只允许横向滚动**：容器设 `min-width`（S2 甘特 ≥ 960px / S1 热力 ≥ 760px / S3 月历 ≥ 900px），内容不重排，此为既定取舍而非缺陷
- [x] **保留 PC 键盘可达性**：`Tab`/`Enter`/`Space` 可完成主要操作、`:focus-visible` 焦点环可见、可点元素为 `<button>` + `aria-label`
- [x] 自查：`grep -rniE "窄屏|移动端|触屏|响应式|平板" views/panorama/` 仅命中 `types.ts` 的「响应式引用」注释（指 Vue 响应式，非响应式布局），**无「需支持移动端」类实现**

---

## 阶段 3（P2 增强）：仅此阶段允许后端改造

> 依赖齐活林对用户 Q4/Q5/Q6 的最终决策；以下三项均为**新增接口**，动后端前先定 spec 与错误码归属。

- [ ] **P2-R1** 借用撤销 `POST /api/borrow-flows/<id>/cancel`：仅借入方本人且状态 = 待审批可撤；撤后释放 `uniq_pending_borrow_flow`
- [ ] **P2-R1** 后端新增 tests（撤销成功 / 非本人 / 非待审批 → 40903 / 42201）
- [ ] **P2-R2** 抢占改期 `PATCH /api/slot-bookings/<id>`：仅本人或 admin；改期后 `(date, template)` 唯一 reserved 仍生效
- [ ] **P2-R2** 后端新增 tests（改期成功 / 越权 40301 / 目标冲突 40904）
- [ ] **P2-R3** 待办聚合 `GET /api/panorama/todos`：**新增** `views/panorama.py`，一次返回待审批数 / 我的抢占数 / 冲突数
- [ ] **P2-R3** 前端 S1/S4 切换到服务端计数，保留前端聚合作降级兜底
- [ ] **P2-R4** 若决策放开同版本互借：改 `borrow_flow_create_view` 校验并重定义冲突语义（**需重跑全量后端测试**）
- [ ] **P2-R5** 若决策做双向互斥：需新建关联模型 → **必须 `makemigrations build_protection_service` 并提交迁移文件**
- [ ] 前端所有 P2 按钮按能力探测 / env 开关隐藏，接口不存在时 UI 优雅降级
- [ ] **（本次新增）P2 前端增强**：中枢接入 `polling.ts` 退避轮询 + `document.hidden` 暂停；S4 刷新按 id 保留勾选；S5「折叠空闲时段」；`?layout=` 深链；5 个布局的组件级 spec

---

## 贯穿项：纪律、文档与回滚

- [x] 动手前通读：`specs/2026-10-10-slot-booking-design.md`、`2026-10-11-weekly-new-design.md`、`2026-10-11-borrow-flow-design.md`、`2026-10-12-scheduling-panorama-prd.md`、本计划对应设计文档
- [x] weekdays 严守 **isoweekday 1-7**，禁止再引入 0 基口径
- [x] 错误码只用既有 10 个；`40901` 保留为策略冲突专用并保留专用弹框
- [x] 状态中文文案单一出处：`views/constants.ts` 的 `bookingStatusMap`（含 available）+ `slotStatusText()`；`DayDetailDialog.vue` 三元硬编码已删除
- [x] 借用复制文案用 VNode 文本渲染，**禁用 `dangerouslyUseHTMLString`**（存储型 XSS）
- [x] `/weekly-new`、`/slot-booking`、`/borrow-flow`、`/strategy` 在阶段 1/2 **一律不删**（回滚兜底；实测仅 `DayDetailDialog.vue` 的展示取值改动，行为不变）
- [x] 每阶段结束后更新设计文档「变更记录」与本计划勾选状态
- [ ] 阶段 1 验收后由齐活林做 Gate Review，通过才开工阶段 2 —— **待人工**

**遗留项（本次未完成，均不阻塞「5 菜单 5 页面」交付）**
1. 5 个布局的组件级 spec（`__tests__/s1~s5*.spec.ts`）——需 `@vue/test-utils` 挂载 + Element Plus stub，工作量约 1~2 人日
2. P0-R1~R6 与「五布局功能等价交叉验收」的人工验收清单执行
3. 深浅色主题下 5 布局的人工目测复核（代码已全走语义变量）
4. 后端测试门禁：本机无 Django 虚拟环境，本次后端零改动故未重跑

**回滚方式**：新增布局全部落在 `views/panorama/` 与 5 行路由注册里 —— 阶段 1/2 任意时点删目录 + 摘路由即可完全回滚，既有 4 个页面与后端全程未动；阶段 3 按 commit revert 端点，前端隐藏按钮降级。

**规模估算**：阶段 1 约 8~10 人日（含 QA）、阶段 2 约 11~15 人日（含 QA）、阶段 3 视决策范围另估；合计前端 + QA 约 19~25 人日，**后端在阶段 1/2 为 0 人日**。实测：阶段 1+2 合计新增 `views/panorama/` 22 个文件 4711 行（含 2 个 spec 共 49 用例），改动既有文件 7 个。
