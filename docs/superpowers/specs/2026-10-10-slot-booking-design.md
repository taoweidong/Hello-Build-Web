# 时段抢占页面设计

日期：2026-10-10
状态：已确认

## 1. 背景与目标

构建策略配置系统（Vue3 + Element Plus + pure-admin-thin 前端，Django + SQLite + DRF 后端）新增「时段抢占」功能模块：管理员提前配置可抢占的时间段模板，全体用户按月查看每天各时段的占用状态，先到先得抢占空闲时段（类似会议室预定）。已被抢占的时段锁定展示抢占人、不可再抢；本人可释放自己的抢占；系统管理员可管理模板并释放任何抢占。

目标：

1. 新增两个独立一级菜单：「时段抢占」（全员，月历抢占 + 状态展示）与「时段配置」（admin，模板管理 + 抢占记录）。
2. 时段模板预配置：名称、起止时间、适用星期、生效日期范围、标识色、排序、启用开关。
3. 月历视图（CSS Grid 自绘）展示每天各时段状态：空闲 / 我的 / 他人锁定 / 已过期 / 非适用日。
4. 点击空闲时段弹窗提交信息抢占：关联版本、关联分支（级联必填）、用途说明，落库保存。
5. 并发抢占由数据库唯一约束兜底，被抢先返回专用错误码 40904，前端提示并自动刷新。
6. 我的抢占抽屉列表 + 释放操作（本人可释自己的；admin 可释任何人的）。

## 2. 关键决策（已与用户确认）

| 决策点 | 结论 |
|--------|------|
| 跨午夜时段 | **不支持**：模板强制 `start_time < end_time`（同日内），模型层约束 + 应用层 42201 双保险 |
| 版本/分支关联 | **必填**：抢占弹窗版本→分支级联必选；后端校验 `branch.version == version`（不匹配 42201） |
| 时段配置入口 | **独立一级菜单**（与抢占页分离，不收进系统管理） |
| 批量抢占 | **明确不做**：一次只能操作一个时段，不设批量端点、不实现圈选 |
| 表格组件选型 | **不引入 AG Grid 及任何新表格库**：月历自绘 CSS Grid（与项目甘特图自绘选型哲学一致），配套列表用项目已有 el-table / @pureadmin/table，零新增依赖 |
| 抢占审批 | 无审批，先到先得 |
| 抢占归属日 | 开始日当天（无跨天语义，与"不支持跨午夜"一致） |
| 过期处理 | 惰性标记：读取时 `date < today` 按 expired 展示，不落定时任务 |
| 视图层范式 | DRF ViewSet `permission_classes = [AllowAny]` + 手动 `authed_user`（reports 模块同款，防 DRF 401 破坏统一响应契约） |
| 错误码 | 沿用现有体系，**新增 40904「时段已被抢占」**（刻意避开 40901 策略冲突专用弹框；40904 落入 http.ts else 分支 ElMessage 提示，无需改基座） |
| 状态管理 | 抢占页页面内 composable（`useSlotCalendar`），不上 Pinia（无跨页共享需求） |

默认假设（未单独确认，可推翻）：

- 可抢占窗口：`date >= today` 且 `date <= today + 60 天`，上限走 `SLOT_BOOKING_HORIZON_DAYS`（settings/env 可配）。
- 用途说明 `purpose` 必填，2~200 字。
- 一人同日可抢多个不同时段，无配额限制。
- 模板重叠策略：同星期下时间区间重叠允许保存，响应返回 `warnings`，前端黄色告警（对齐项目"冲突不阻止保存但告警"哲学）。
- admin 释放他人抢占必须填写释放原因；本人释放原因为可选。

## 3. 技术选型结论（AG Grid 及替代表格组件）

**AG Grid Vue Data Grid**：Community 版（MIT）提供行列虚拟化、排序/筛选/行选择/单元格编辑、列固定与重排、自定义 cellRenderer（可挂 Vue 组件）、CSV 导出、无障碍；Enterprise 版（商业付费）增加行分组聚合、透视表、Master/Detail、Excel 导出、剪贴板、集成图表。其价值兑现前提是大数据量、Excel 式批量编辑、分组聚合分析。

**本页不引入的论证**：

| 判据 | 本页实际情况 | 结论 |
|---|---|---|
| 数据规模 | 31 天 × 3~6 段 ≈ 100–200 个状态单元 | 虚拟化完全用不上 |
| 交互形态 | 状态芯片点击 + 弹窗表单（月历矩阵） | 不是表格数据的排序/筛选/批量编辑 |
| 样式体系 | 项目全线 Element Plus | AG Grid 独立主题系统融合成本高 |
| 项目先例 | 甘特图已选自绘 DIV/CSS | 自绘与项目选型哲学一致 |

十款替代表格组件逐一裁决：VXE Table 唯一留观（国产 MIT、中文文档，未来大矩阵 + 批量编辑场景首选）；RevoGrid（百万格虚拟化）、TanStack（无头需自写 UI）、PrimeVue/Naive UI/Vuetify/Quasar（生态绑定冲突）、vue3-easy-data-table（el-table 子集）均排除；**Handsontable 因商业许可风险直接排除**（内部业务系统属商业用途，需付费授权）。

**撤销条件**（出现任一即重启选型，候选顺序 VXE Table → AG Grid Community）：① 资源 × 日期矩阵单元格 > 2000 同屏；② 需要 Excel 式批量圈选抢占/复制粘贴；③ 需要跨月聚合统计透视。

## 4. 数据模型

新增领域文件 `backend/build_protection_service/models/slot_booking.py`，并在 `models/__init__.py` 统一导出。

```
SlotTemplate（时间段模板 · 提前配置）
├── name               CharField(50)              时段名称（如"上午构建窗口"），重名 40902
├── start_time         TimeField                  每日开始（HH:MM）
├── end_time           TimeField                  每日结束，强制 > start_time（同日）
├── weekdays           CharField(20, blank)       适用星期 "1,2,3,4,5"（1=周一…7=周日），空=每天
├── effective_from     DateField(null, blank)     生效起始日
├── effective_to       DateField(null, blank)     生效截止日
├── color              CharField(20, default)     标识色（预设 Element Plus 色阶 8 选 1）
├── sort_order         IntegerField(default=0)    日历芯片展示顺序
├── enabled            BooleanField(default=True) 停用不删数据，日历不再渲染
├── created_at / updated_at

SlotBooking（抢占记录）
├── date               DateField                  抢占日期（YYYY-MM-DD）
├── template           FK(SlotTemplate, PROTECT, related_name="bookings")
├── start_snapshot     TimeField                  模板开始时间快照
├── end_snapshot       TimeField                  模板结束时间快照
├── status             CharField(10)              reserved / released（过期不落库：date<today 的 reserved 由前端按日期惰性置灰，无 expired 枚举值；2026-10-12 移除死枚举）
├── user               FK(User, PROTECT, related_name="slot_bookings")   抢占人
├── purpose            CharField(200)             用途说明（2~200 字）
├── version            FK(Version, PROTECT, related_name="slot_bookings")  必填
├── branch             FK(Branch, PROTECT, related_name="slot_bookings")   必填，校验归属所选版本
├── created_at         DateTimeField(auto_now_add)  抢占时刻
├── released_at        DateTimeField(null)          释放时刻
├── release_reason     CharField(200, blank)        释放原因（admin 释放必填）

约束与索引：
├── UniqueConstraint(fields=["date", "template"],
│                     condition=Q(status="reserved"), name="uniq_slot_booking_active")
│   —— SQLite partial unique index，数据库层根绝并发双抢
└── 普通索引：SlotBooking (date)、SlotBooking (user, status)
```

设计要点：

- **时间快照**：抢占落库时复制模板的起止时间，管理员后续改模板时间不影响历史抢占展示（与时间序列化格式统一策略配套：日期 `YYYY-MM-DD`、时间 `HH:MM`、时刻 `"%Y-%m-%dT%H:%M:%S"`）。
- **PROTECT 外键**：抢占记录是事实数据，版本/分支/模板被删会导致记录失义；Django 保护拦截删除，与项目 `pm_user` 用 PROTECT 的先例一致。
- **删除模板规则**：存在任何抢占记录 → 40902 拦截并提示改用「停用」；无记录才允许物理删除。

## 5. API 契约

挂载 `/api`，沿用统一响应 `{code, message, data}`（`api.py` 的 `ok()/err()`；视图辅助 `views/__init__.py` 的 `authed_user`/`json_resp`/`parse_body`）。

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/slot-templates` | 启用模板列表（日历渲染用） | 登录用户 |
| POST | `/slot-templates` | 新建模板；重叠时 200 返回 `{template, warnings[]}` | admin |
| PUT | `/slot-templates/{id}` | 修改模板（返回结构同 POST） | admin |
| DELETE | `/slot-templates/{id}` | 删除模板；存在抢占记录 40902 拦截 | admin |
| GET | `/slot-calendar?month=YYYY-MM` | **单次聚合**返回该月 31 天 × N 模板状态矩阵（后端 2 次查询组装） | 登录用户 |
| POST | `/slot-bookings` | 抢占 `{date, template_id, purpose, version_id, branch_id}` | 登录用户 |
| POST | `/slot-bookings/{id}/release` | 释放 `{release_reason?}`（admin 必填原因） | 本人或 admin |
| GET | `/slot-bookings/mine` | 我的抢占（分页，page_size 默认 20 最大 100） | 登录用户 |
| GET | `/slot-bookings?date_from&date_to&version_id&branch_id&user_id&status&page` | 全部记录筛选列表（配置页 Tab②） | admin |

`GET /slot-calendar` 应答结构：

```json
{
  "code": 0, "message": "ok",
  "data": {
    "month": "2026-10",
    "horizon_days": 60,
    "templates": [
      { "id": 1, "name": "上午窗口", "start_time": "08:00", "end_time": "12:00",
        "weekdays": "1,2,3,4,5", "color": "#67c23a", "sort_order": 1 }
    ],
    "days": {
      "2026-10-14": [
        { "template_id": 1, "status": "reserved",
          "booking": { "id": 9, "user_name": "张三", "purpose": "27A 回归",
                       "version_name": "27A", "branch_name": "master",
                       "is_mine": false, "created_at": "2026-10-10T09:12:00" } }
      ]
    }
  }
}
```

`days` 仅包含该月内存在启用模板的日期；`is_mine` 由服务端按请求用户计算。抢占成功（POST）响应返回该 booking 完整对象，前端据此就地翻转芯片状态。

### 5.1 抢占校验链（后端，transaction.atomic 内）

1. 模板存在且 `enabled`（42201）；
2. `date` 合法：`>= today` 且 `<= today + SLOT_BOOKING_HORIZON_DAYS`（42201，"已过期"/"超出可抢窗口"）；
3. 模板 `weekdays` 匹配该日星期（42201）、`effective_from/to` 覆盖该日（42201）；
4. `version_id`/`branch_id` 存在且 `branch.version_id == version_id`（42201，"分支不属于所选版本"）；
5. `purpose` 2~200 字（42201）；
6. 写入触发唯一约束，`IntegrityError` 捕获转 **40904**「该时段刚被 {抢占人} 抢占」（status 409）。

POST 非幂等：靠唯一约束防重 + 前端按钮 loading 防连点。前端校验只是体验层，后端每条独立兜底。

## 6. 权限设计

| 操作 | 系统 admin | pm/builder/tester/integrator |
|------|:---:|:---:|
| 查看日历 / 模板列表 / 我的抢占 | ✓ | ✓ |
| 抢占 | ✓ | ✓ |
| 释放自己的抢占 | ✓ | ✓ |
| 释放他人抢占（必填原因） | ✓ | ✗（40301） |
| 模板 CRUD / 全部抢占记录 | ✓ | ✗（40301） |

- 前端按角色隐藏入口（配置菜单 `meta.roles = ADMIN_ROLE`、释放按钮显隐），后端每个写接口独立校验，不依赖前端隐藏。

## 7. 前端设计

### 7.1 路由与菜单

在 `frontend/src/router/asyncRoutes.ts` 新增两个一级菜单（排在现有菜单末尾，rank 以文件现状最大值递增，暂定 11/12）：

| 路由 | 名称 | rank | meta.roles | 图标 | 说明 |
|------|------|------|------------|------|------|
| `/slot-booking` | SlotBooking | 11 | ALL_ROLES | ep/alarm-clock | 月历抢占页，单页无子路由 |
| `/slot-config` | SlotConfig | 12 | ADMIN_ROLE | ep/setting | 配置管理页，两 Tab |

### 7.2 页面一「时段抢占」（月历页）

```
┌───────────────────────────────────────────────────────────────────┐
│ 工具栏卡片                                                          │
│ [◀] 2026年10月 [▶] [今天]     本月 62 段 · 已占 18 段 · 我的 3 段     │
│ 图例: ●空闲  ★我的  🔒已抢占  ▒已过期  — 非适用日      [我的抢占]    │
├───────────────────────────────────────────────────────────────────┤
│ 月历卡片（CSS Grid：7 列 × 5~6 行 = 42 格，含上下月补位灰格）        │
│ 单日格：日期角标（今日 primary 圆形高亮；周末列底 fill-color-lighter）│
│         + 芯片列表（按模板 sort_order；>5 段折叠为「+N 更多」）       │
│ 芯片左侧 3px 色条 = 模板标识色                                       │
└───────────────────────────────────────────────────────────────────┘
```

交互流：

```
进入页面 → 读 URL ?month=YYYY-MM（无则当月）→ GET /slot-calendar 单次聚合
  ├─ Loading: 42 格骨架屏（el-skeleton）
  ├─ Empty: 无启用模板 → 空状态（admin 显示[去配置]CTA / 其余显示引导文案）
  └─ Error: 错误态 + [重试]

点击[●空闲芯片] → 抢占弹窗 → 提交
  ├─ 成功: 关弹窗 + ElMessage.success + 芯片翻转[★我的]（300ms 状态闪烁）
  └─ 40904: ElMessage.error("该时段刚被张三抢占") + 自动重拉当月日历

点击[★我的芯片] → Popover 详情 + [释放]（二次确认）
点击[🔒他人芯片] → 只读详情弹窗（抢占人/用途/版本分支/抢占时刻）
点击[+N 更多] → 当日详情弹窗（该日全时段大卡列表）
点击[我的抢占] → 右侧抽屉: 未来抢占列表 + 释放入口（二次确认）
切换月份/点[今天] → 更新 URL query（可深链分享、刷新保持位置）+ 重拉数据
```

芯片 8 状态：

| 状态 | 视觉（全部走 Element Plus token） | 交互 |
|---|---|---|
| 空闲 | `success-light-9` 底 + `success-light-5` 边框 + 模板色条 | hover 上浮 1px+阴影；点击开抢占弹窗 |
| 我的 | `--el-color-primary` 实底白字 + ★ | 点击开详情 Popover（可释放） |
| 他人锁定 | `--el-fill-color` 灰底 + 🔒 + 抢占人姓氏 | `cursor:not-allowed`；tooltip 抢占人/用途 |
| 已过期 | 整格 `opacity:.45` | 不可交互，tooltip "已过期" |
| 非适用日 | 格内浅色 "—" | 无 |
| Loading / Empty / Error | 见交互流 | — |

抢占弹窗：只读回显日期/星期/时段/时长；表单为关联版本（select 必选，getPlan() 数据源）→ 关联分支（select 必选，随版本联动，切换版本清空）→ 用途说明（textarea 2~200 字，计数）；警示文案"抢占后不可修改；如需调整请先释放"；提交按钮 loading 防连点。

组件拆分（`src/views/slot-booking/`）：

```
index.vue                  # 容器：month 状态、URL 同步、聚合数据、统计计算
components/
├── MonthGrid.vue          # 月历网格（42 格、周对齐、补位、骨架屏）
├── DayCell.vue            # 单日格：日期角标 + 芯片列表 + "+N"折叠
├── SlotChip.vue           # 芯片：状态渲染与点击分发（纯展示）
├── BookingDialog.vue      # 抢占弹窗（版本/分支级联必填）
├── SlotDetailDialog.vue   # 详情弹窗（我的→可释放 / 他人→只读）
├── DayDetailDialog.vue    # "+N"当日全时段大卡列表
└── MyBookingsDrawer.vue   # 我的抢占抽屉
```

状态用页面内 composable `useSlotCalendar`（month/calendarData/loading/load），不上 Pinia。

### 7.3 页面二「时段配置」（admin）

el-tabs 两 Tab：

- **Tab 1 模板管理**：el-table（名称、时段、适用星期 tag、生效范围、色条预览、排序、启用 switch、操作）；新建/编辑弹窗表单：名称（重名 40902）、起止时间（el-time-picker，**强制 start < end，跨天直接校验失败提示"不支持跨天时段"**）、适用星期（多选，空=每天）、生效范围（可空）、标识色（预设色板 8 选 1）、排序、启用开关。同星期重叠允许保存但响应带 `warnings` 黄色告警。删除有记录的模板 40902 拦截并提示改用停用。
- **Tab 2 抢占记录**：筛选（日期范围/版本/分支/抢占人/状态）+ el-table 分页列表（日期、时段、用途、版本-分支、抢占人、抢占时间、状态、操作[释放]）；admin 释放需二次确认并填释放原因。

### 7.4 视觉与可访问性

- 设计三旋钮：VARIANCE 3 · MOTION 2 · DENSITY 7，数据密集风，与既有系统同源；颜色全部走 Element Plus CSS 变量，禁止硬编码。
- 动效仅 `transform/opacity`：hover 上浮 150ms、月切换 fade、抢占成功状态闪烁 300ms；尊重 `prefers-reduced-motion`。
- 可访问性：芯片用 `<button>` + aria-label（如"10月14日 08:00-12:00 上午窗口，可抢占"）；状态不只靠颜色（★/🔒 图标 + 文案冗余）；`:focus-visible` 即时聚焦环；弹窗 Esc 关闭；对比度 WCAG AA。
- 响应式：<768px 月历降级为按天聚合的纵向卡片列表，触控热区 ≥40px（桌面 24px）。

### 7.5 API 封装与类型

新增 `frontend/src/api/slotBooking.ts`（走 `src/api/http.ts` 基座）：TypeScript 类型 SlotTemplate/SlotBookingItem/CalendarDayItem/CalendarResponse 内聚于此文件；版本/分支下拉复用 `getPlan()`（`src/api/plan.ts`）。

## 8. 错误处理

| code | 场景 | 前端表现 |
|---|---|---|
| 40100 | 未认证 | 拦截器跳登录（已有） |
| 40301 | 非 admin 动模板/记录、释放他人抢占 | 「无权限执行该操作」（已有） |
| 40401 | 模板/抢占不存在 | 提示并刷新（已有） |
| 42201 | 起止非法/跨天、日期过期、超可抢窗口、weekdays 不匹配、branch≠version、purpose 非法、admin 释放未填原因 | 提示后端 message（已有） |
| 40902 | 模板重名、删除有记录模板 | ElMessage 提示（已有） |
| **40904（新增）** | **时段已被抢占**（并发兜底），message 带抢占人姓名 | ElMessage 提示 + 自动刷新月历（落入 http.ts else 分支，无需改基座） |

## 9. 测试计划

**后端**（`build_protection_service/tests_slot_booking.py`，Django TestCase，参照 tests_branch_config.py 风格）：

- 模型约束：同一 (date, template) 两条 reserved 触发 IntegrityError；released 后同日同段可再抢；跨天模板（start >= end）被约束/校验拒绝
- 抢占校验链：过期日期、超 60 天窗口、weekdays 不匹配、模板停用、branch-version 不匹配、purpose 越界 → 42201
- 并发兜底：绕过应用校验直接插入后抢占 → 40904
- 释放：本人可释；他人释放 40301；admin 释他人必填原因；释放后日历该格回到空闲
- 日历聚合：42 格数据正确性、is_mine 计算、惰性过期展示、月边界（6 周跨月）
- 模板管理：重名 40902、删除有记录模板 40902、重叠 warnings 返回
- 权限矩阵：非 admin 访问模板写接口/记录列表 40301

**前端**：

- `npm run typecheck` 通过
- 浏览器手动联调：配置模板 → 月历抢占（成功翻转）→ 双开浏览器并发抢同段验证 40904 提示与自动刷新 → 释放 → 我的抢占抽屉 → 切换角色验证菜单与按钮显隐

## 10. 明确不做（边界声明）

- ❌ 跨午夜/跨天时段（模型层强制同日）
- ❌ 批量抢占、圈选、Excel 导入（一次一个时段）
- ❌ 抢占审批流（先到先得）
- ❌ 与策略互斥检测（40902）联动——时段抢占是独立资源池
- ❌ 引入 AG Grid/VXE 等新表格库（撤销条件见 §3）
- ❌ 定时任务过期清理（惰性标记即可）


## 修订记录（2026-10-12 第二轮质量优化）

- **weekdays 统一为 isoweekday 1-7（1=周一…7=周日）**：序列化器校验原为 0-6（0=周一），与服务层 `isoweekday()` 匹配、模型 help_text、seed、前端选项冲突，曾致 UI 无法创建周日模板、填 0 静默失效；现已全链路统一 1-7。
- **SlotBooking 状态枚举移除死值 `expired`**：过期采用惰性展示（前端按日期置灰），从未落库；admin 记录列表 `status` 筛选增加值域校验（仅 reserved/released，非法值 42201），前端 RecordsPanel 同步移除「已过期」筛选项。
