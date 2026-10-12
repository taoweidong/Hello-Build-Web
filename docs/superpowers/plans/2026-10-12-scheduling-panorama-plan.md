# 调度全景展示 实施计划（checkbox）

| 项 | 内容 |
|---|---|
| 日期 / 撰写 / 状态 | 2026-10-12 / 高见远（架构师） / 待评审后开工 |
| 设计文档（唯一口径出处） | `docs/superpowers/specs/2026-10-12-scheduling-panorama-design.md` |
| PRD（业务需求出处） | `docs/superpowers/specs/2026-10-12-scheduling-panorama-prd.md` |
| 责任人 | 齐活林（主理人·编排验收） / 许清楚（产品经理·口径） / 高见远（架构师·文档裁定） / 寇豆码（工程师·前后端实现） / 严过关（QA·测试） |
| 铁律 | **任何阶段只要改动了代码，必须先跑测试全绿才允许提交**（AGENTS.md 强制）。模型改动必须 `makemigrations build_protection_service` 并提交迁移。 |

**测试门禁基线（每次提交前必跑）**
- [ ] 后端：`cd backend && python manage.py test build_protection_service` —— **≥ 279 全绿**
- [ ] 前端：`cd frontend && npm run test` —— 基线 ≥ 104；本计划 Phase 1 后 ≥ 108、Phase 2 后 ≥ 112
- [ ] 涉及类型/模板改动：`npm run typecheck` 通过
- [ ] 涉及构建产物：`npm run build` 通过
- [ ] 模型若改动：`python manage.py makemigrations build_protection_service` 且迁移文件随代码提交

---

## 阶段 0：口径裁定与前置准备（阻塞 Stage 1，必须先落地）

> 责任人：许清楚（答复）+ 高见远（记录到设计文档 §6）+ 齐活林（确认）

- [ ] **Q1** 裁定：builder/tester/integrator 是「只读 + 可借用 + 可抢占」还是「完全只读」（架构推荐：前者）
- [ ] **Q2** 裁定：抢占在全景页**直接做**（保留 `/slot-booking` 作深链兜底）
- [ ] **Q3** 裁定：5 布局**全员可切换** + localStorage 记住，默认落 `/panorama/month`
- [ ] **Q4** 裁定：是否放开同版本内分支互借（架构建议：**先不放开**）
- [ ] **Q5** 裁定：是否做策略 ↔ 抢占双向互斥联动（架构建议：**不做**，仅前端视觉叠加）
- [ ] **Q6** 裁定：S4 红点走前端聚合还是新增接口（建议 Phase 1/2 前端聚合）
- [ ] **Q7** 裁定：借用是否支持转交 / 代批（建议：不支持，admin 全量覆盖）
- [ ] **Q8** 裁定：过期判定**按格子**（历史格只读、未来格可改）
- [ ] **Q9（本文补）** 裁定：现有 `/weekly-new`（周×时刻矩阵）**保留不动**还是后续重定向
- [ ] **Q10（本文补）** 裁定：借用事件时间轴锚点定**发起日 `created_at`**（`BorrowFlow` 无执行日字段）
- [ ] 将 Q1~Q10 结论回填 PRD §6 与设计文档 §6，两文档口径**逐字一致**
- [ ] 确认零新增依赖红线：`echarts` 仅在确需图表时由架构师书面批准后才 `use()`；本次 5 布局**默认不启用**

---

## 阶段 1（P0 打底）：同构事件 + 数据中枢 + 动作总线 + S3 月历矩阵

> 目标：让 PRD 的 **P0-R1~R6** 四场景在 **1 个布局（S3）** 上完整闭环。**本阶段后端零改动、无 migration。**
> 主要责任人：寇豆码（实现）；严过关（测试）；高见远（抽象层定型）

### 1.1 口径与基建（1.5 人日）
- [ ] `src/views/constants.ts` **新增** `slotStatusMap`（reserved→已抢占 / released→已释放 / available→空闲）与取值函数 `slotStatusText(code)`，风格对齐既有 `borrowStatusMeta`
- [ ] 改造 `views/slot-booking/components/{DayDetailDialog,MyBookingsDrawer}.vue` 与 `views/slot-booking/index.vue`，删除三元硬编码，改取 `slotStatusMap`
- [ ] `src/store/constants.ts` **新增** `panoramaLayoutKey`（localStorage 键，命名沿用 `businessUserKey` 风格）
- [ ] `src/utils/week.ts` **新增** `buildDateRange(start, end)` 纯函数（生成连续 `YYYY-MM-DD` 日期轴，替代固定 7 天）
- [ ] 补 `views/__tests__/constants.spec.ts` 用例锁定新映射；补 `utils/__tests__/week.spec.ts` 日期轴用例（跨月/跨周/闰年）

### 1.2 同构事件与数据中枢（3~4 人日）
- [ ] **新增** `views/panorama/types.ts`：`ScheduleSource` / `ScheduleKind` / `SchedulePermissions` / `ScheduleEvent` / `AgendaItem` / `ScheduleDay` / `ScheduleKpi`（字段逐项对齐设计文档 §5.1.1）
- [ ] **新增** `views/panorama/sources/strategySource.ts`：`WeeklyStrategy` × 日期 → 最多 4 个事件；阶段区间走 `GET /api/plan?date=` 的 `timeline` **懒加载**；**禁止前端硬算 `build_minutes`**
- [ ] **新增** `views/panorama/sources/slotSource.ts`：`SlotCalendarResponse` 的「有模板的 date × template」→ 1 事件；`is_mine` 取服务端；过期用 `isPastSlot(date, end_time)`
- [ ] **新增** `views/panorama/sources/borrowSource.ts`：`BorrowFlowItem` → 借用事件，锚发起日；**不臆造执行日字段**
- [ ] **新增** `views/panorama/useScheduleData.ts`：三源并发编排 + **自增序号守卫丢弃过期响应** + `document.hidden` 暂停 + `silent:true` 轮询（`pollDelay` 30s→300s 退避）
- [ ] **新增** `views/panorama/selectors.ts`（纯函数）：`heat()` / `lanes()` / `lanePack()` / `matrix()` / `agenda()` / `kpi()`
- [ ] **新增** `views/panorama/usePanoramaFilter.ts`：时间范围 / 版本 / 分支多选 / 状态 / 仅看我的 统一状态
- [ ] **新增** `views/panorama/context.ts`：provide/inject CTX，5 路由共享同一 hub 实例
- [ ] `useWeeklyPanorama.ts` **保持不动**（`/weekly-new` 回归基线），仅在设计文档标注「冻结不再迭代」

### 1.3 动作总线（1.5 人日）
- [ ] **新增** `views/panorama/useScheduleActions.ts`：六动作 `edit/borrow/occupy/release/approve/reject` + `copyText` + `batchRelease`
- [ ] 每个动作内做 `permissions` 二次校验（前端隐藏 ≠ 可靠，后端仍独立校验）
- [ ] 40901 → `ElMessageBox.alert` 专用弹框；40904/40903 → 自动重拉当月；40301/42201/40401/42901 → `ElMessage`（文案取后端 `message`）
- [ ] 成功后统一 `onDirty()` → `refresh()`；**任何页面不得自行 `import` 业务 API**
- [ ] **新增** `views/panorama/shared/ScheduleEventCard.vue`：`<button>` + `aria-label` + 状态图标（**状态不靠颜色单独表达**）
- [ ] **新增** `views/panorama/shared/PanoramaFilterBar.vue`：五布局共用筛选栏

### 1.4 S3 月历矩阵页面（1.5~2 人日）
- [ ] **新增** `views/panorama/layouts/s3-month/index.vue`（第一个完整布局）
- [ ] **改造** `views/slot-booking/components/{MonthGrid,DayCell,SlotChip}.vue`：加「非抢占事件标记」slot，**不得破坏 `/slot-booking/index` 现有行为**
- [ ] **新增** `views/panorama/shared/StrategyMarker.vue`：日格上的策略/借用标记（优先级 抢占 > 借用 > 策略，超出「+N」折叠）
- [ ] **新增** `views/panorama/shared/BorrowApprovalDrawer.vue`：场景 D 红点 + 审批抽屉（通过 / 驳回必填意见）
- [ ] 路由注册：`/panorama` 父菜单（rank 16，`meta.roles = ALL_ROLES`）+ `/panorama/month`（其它 4 个子路由本阶段先留占位注释）
- [ ] 局部视觉：建 `.s3-scope` 作用域并局部覆盖 `--el-*`（照搬 `views/weekly-report/theme.scss` 手法），与全局 `html.dark` 互不干扰

### 1.5 阶段 1 测试与验收（QA 严过关）
- [ ] **新增** `views/panorama/__tests__/types.spec.ts`：事件归约幂等、id 稳定性
- [ ] **新增** `views/panorama/__tests__/sources.spec.ts`：三源映射（含 `/plan` 为空降级、过期 `past`、isoweekday 1-7）
- [ ] **新增** `views/panorama/__tests__/selectors.spec.ts`：`heat/lanes/lanePack/matrix/agenda/kpi` 纯函数
- [ ] **新增** `views/panorama/__tests__/permissions.spec.ts`：5 角色 × 4 场景权限包矩阵（对齐 PRD 权限矩阵）
- [ ] **新增** `views/panorama/__tests__/s3-month.spec.ts`：四场景在 S3 内闭环
- [ ] 补 `composables/__tests__/useWeeklyPanorama.spec.ts` 基线（防止本次重构误伤既有页）
- [ ] 跑通 P0-R1~R6 全项人工验收清单（`docs/superpowers/plans/` 旁附验收记录）

---

## 阶段 2（P1 铺开）：S1 / S2 / S4 / S5 + 切换器 + 叠加 + 批量 + 无障碍

> 目标：PRD **P1-R1~R5**。依赖阶段 1。**本阶段后端仍零改动、无 migration。**
> 主要责任人：寇豆码（实现）；严过关（测试）

### 2.1 S1 调度大屏态势视图（2~3 人日）
- [ ] **新增** `views/panorama/layouts/s1-dashboard/index.vue`
- [ ] **新增** `layouts/s1-dashboard/KpiCards.vue`：今日构建 / 本周抢占 / 待我审批 / 冲突告警（点击下钻 S3、S4）
- [ ] **新增** `layouts/s1-dashboard/LoadHeatmap.vue`：时刻 × 周一~周日 CSS Grid 热力，色深 = 事件数
- [ ] **新增** `layouts/s1-dashboard/{AlertList,TodoQueue}.vue`：告警 Top N + 待办队列（批量释放 / 批量驳回入口）
- [ ] 工具栏：投屏模式（`useFullscreen`）+ 自动刷新（`polling.ts` 退避 + `document.hidden` 暂停）
- [ ] 冲突 KPI **仅取锚点日**的 `/api/plan` `conflict`，UI 明示「今日」范围（不做全周 7 次调用）
- [ ] **新增** `views/panorama/__tests__/s1-dashboard.spec.ts`

### 2.2 S2 时空甘特视图（3~4 人日）
- [ ] **新增** `views/panorama/layouts/s2-gantt/index.vue`
- [ ] **新增** `layouts/s2-gantt/{LaneRow,TimeAxisRuler,PhaseBar,GanttLegend}.vue`（阶段色复用 `components/gantt/types.ts::STAGE_COLORS`）
- [ ] 泳道 = 分支（按版本分组），百分比绝对定位；**「仅看有任务分支」开关**（无虚拟滚动，行 > 60 有 DOM 压力）
- [ ] 默认**单日**；周模式默认关闭，开启时才并发 ≤ 7 次 `/api/plan`
- [ ] 窄屏降级：强制 `min-width` + 横向滚动 + 明确提示
- [ ] **新增** `views/panorama/__tests__/s2-gantt.spec.ts`

### 2.3 S4 分组列表看板视图（2~3 人日）
- [ ] **新增** `views/panorama/layouts/s4-board/index.vue`
- [ ] **新增** `layouts/s4-board/{GroupSection,EventRow,BatchBar,BoardDrawer}.vue`
- [ ] 分组维度可切：版本 / 分支 / 状态；每组默认收起、每组 ≤ 50 条、超出提示筛选
- [ ] 批量：**串行循环既有单条接口** + 逐条成功/失败汇总，**失败项保留**（P1-R4），禁止批量接口
- [ ] 刷新**按 id 保留 selection**，避免轮询打断勾选
- [ ] **新增** `views/panorama/__tests__/s4-board.spec.ts`

### 2.4 S5 时间轴流水视图（2~3 人日）
- [ ] **新增** `views/panorama/layouts/s5-timeline/index.vue`
- [ ] **新增** `layouts/s5-timeline/{DayTrack,HourTick,AgendaRow,ConflictBadge}.vue`
- [ ] CSS Grid `repeat(96, 8px)` = 15 分钟粒度；重合事件左右分列复用 `selectors.lanePack()`；> 3 条降级「+N」
- [ ] 「只看我的 / 只看冲突 / 只看借用」三态；「折叠空闲时段」开关
- [ ] 单页接入 30s 近实时轮询（退避 + `document.hidden` 暂停 + `silent:true`）
- [ ] **新增** `views/panorama/__tests__/s5-timeline.spec.ts`

### 2.5 布局切换器与跨布局能力（1.5 人日）
- [ ] **新增** `views/panorama/LayoutSwitcher.vue`：5 段式互跳，`router.push` + 写 localStorage（`panoramaLayoutKey`）
- [ ] `/panorama` 无子路径时按偏好重定向；无偏好落 `/panorama/month`
- [ ] 深链解析优先级 `query.layout > localStorage > month`（P1-R1）
- [ ] 四路由全量注册到 `router/asyncRoutes.ts`（`meta.roles = ALL_ROLES`）
- [ ] 五布局各自 `.s1-scope` ~ `.s5-scope` 局部 `--el-*` 覆盖，互不干扰
- [ ] 跨源叠加同画布显示（P1-R3）：策略块 + 已抢占时段重合处加冲突标记，**仅视觉提示，不触碰后端互斥逻辑**
- [ ] 无障碍（P1-R5）：芯片为 `<button>` + `aria-label`、焦点环可见、对比度抽样达 WCAG AA、状态不靠颜色单独表达
- [ ] 五布局**功能等价交叉验收**：同一份数据下四场景在 5 个布局逐一走通

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

---

## 贯穿项：纪律、文档与回滚

- [ ] 动手前通读：`specs/2026-10-10-slot-booking-design.md`、`2026-10-11-weekly-new-design.md`、`2026-10-11-borrow-flow-design.md`、`2026-10-12-scheduling-panorama-prd.md`、本计划对应设计文档
- [ ] weekdays 严守 **isoweekday 1-7**，禁止再引入 0 基口径
- [ ] 错误码只用既有 10 个；`40901` 保留为策略冲突专用并保留专用弹框
- [ ] 状态中文文案只用既有 9 个，全部经 `views/constants.ts` 单点出（验收：`grep -rn "已抢占\|已释放" views/` 命中仅 1 处）
- [ ] 借用复制文案用 VNode 文本渲染，**禁用 `dangerouslyUseHTMLString`**（存储型 XSS）
- [ ] `/weekly-new`、`/slot-booking`、`/borrow-flow`、`/strategy` 在阶段 1/2 **一律不删**（回滚兜底）
- [ ] 每阶段结束后更新设计文档「变更记录」与本计划勾选状态
- [ ] 阶段 1 验收后由齐活林做 Gate Review，通过才开工阶段 2

**回滚方式**：新增布局全部落在 `views/panorama/` 与 5 行路由注册里 —— 阶段 1/2 任意时点删目录 + 摘路由即可完全回滚，既有 4 个页面与后端全程未动；阶段 3 按 commit revert 端点，前端隐藏按钮降级。

**规模估算**：阶段 1 约 8~10 人日（含 QA）、阶段 2 约 11~15 人日（含 QA）、阶段 3 视决策范围另估；合计前端 + QA 约 19~25 人日，**后端在阶段 1/2 为 0 人日**。
