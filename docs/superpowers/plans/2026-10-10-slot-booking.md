# 时段抢占模块实施计划

> **状态（2026-10-12 补记）**：本计划所述功能已全部实施合入（2026-10-10/11 提交 ae69610…4ec2477、e4d9a05 等），下方 checkbox 为执行期未及时回填的历史状态，不再维护；现行行为以设计文档与代码为准。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「时段抢占」模块：管理员预配置时间段模板（时段配置页），全员在月历页按月查看每天各时段占用状态，点击空闲时段弹窗抢占（关联版本/分支必填），先到先得，唯一约束兜底并发双抢（40904），本人/admin 可释放。

**Architecture:** 后端新增 `SlotTemplate`/`SlotBooking` 两表（领域文件 `models/slot_booking.py`，partial unique condition 约束防双抢），服务层组装月历聚合与抢占事务；视图层 DRF ViewSet + `AllowAny` + 手动 `authed_user`（reports 模块同范式）。前端新增两个一级菜单：`/slot-booking`（全员，自绘 CSS Grid 月历 + 芯片 + 弹窗/抽屉）与 `/slot-config`（admin，模板管理 + 抢占记录两 Tab），API 封装 `src/api/slotBooking.ts`。

**Tech Stack:** Django 5 + DRF + SQLite / Vue 3 + Element Plus + pure-admin-thin / 统一响应契约 `{code, message, data}`。

**设计文档:** `docs/superpowers/specs/2026-10-10-slot-booking-design.md`（字段定义、接口契约、交互与视觉规范以此为准，本计划不重复）。

---

## 0. 执行者必读上下文

**项目结构**：
- 后端 app `backend/build_protection_service/`：模型按领域拆分（`models/others.py` / `models/report.py` / `models/branch_config.py`）；本模块新增 `models/slot_booking.py`。
- 后端测试：Django TestCase 风格（见 `tests.py`、`tests_branch_config.py`），运行命令（在 `backend/` 下）`python manage.py test build_protection_service -v 2`；本模块测试文件 `tests_slot_booking.py`。
- 前端：Vue3 + TypeScript，API 封装在 `src/api/*.ts` 并以 `src/api/http.ts`（Axios 拦截器）为基座；页面在 `src/views/`，业务路由静态注册于 `src/router/asyncRoutes.ts`。

**与本任务相关的事实**：
- `views/__init__.py` 提供 `authed_user(request) -> (user, error_resp)`、`json_resp(payload, status=200)`（`ensure_ascii=False`）、`parse_body(request)`。
- `api.py` 提供 `ok(data=None, message="ok")`、`err(code, message)`。
- DRF 全局 `IsAuthenticated` 只放行；每个 ViewSet 均需 `permission_classes = [AllowAny]` 并手动 `authed_user` 校验（见 `views/reports.py` 注释原因：未认证时 DRF 返回无 code 的 401，破坏契约）。
- 错误码：40100 未认证、40301 无权限、40401 不存在、42201 参数非法、40902 重名/删除拦截、**新增 40904 时段已被抢占**（落入 http.ts else 分支 ElMessage 提示；**严禁使用 40901**——那是策略时间冲突专用弹框码）。
- 时间序列化：日期 `YYYY-MM-DD`、模板时间 `HH:MM`、时刻 `"%Y-%m-%dT%H:%M:%S"`。
- week 值约定：`weekdays` 存 `"1,2,3,4,5"`，1=周一 … 7=周日（对齐 Python `isoweekday`）。
- 抢占弹窗的版本/分支下拉复用 `getPlan()`（`src/api/plan.ts`，所有角色可访问），取 `version_id/version_name` 与分支归属。
- 新增 settings 项 `SLOT_BOOKING_HORIZON_DAYS = int(os.getenv("SLOT_BOOKING_HORIZON_DAYS", "60"))`。
- seed 命令守卫锚点模式：以根实体存在性判断是否补种（参考 `management/commands/seed.py` 的 Version「27A」锚点注释）。
- 提交信息用简体中文；模型字段中文 verbose_name；注释简体中文。
- 用户已确认边界（不要实现）：不支持跨午夜时段、不支持批量抢占、无审批流、不与策略互斥检测联动。

**文件结构映射**：

| 文件 | 职责 | 操作 |
|---|---|---|
| `backend/.../models/slot_booking.py` | SlotTemplate / SlotBooking 两表 + partial unique 约束 | 新建 |
| `backend/.../models/__init__.py` | 统一导出新模型 | 修改 |
| `backend/config/settings.py` | `SLOT_BOOKING_HORIZON_DAYS` 配置项 | 修改 |
| `backend/.../services/slot_booking.py` | 月历聚合、抢占事务、释放、重叠检测、惰性过期 | 新建 |
| `backend/.../serializers/slot_booking.py` | 模板/抢占入参校验 | 新建 |
| `backend/.../views/slot_booking.py` | SlotTemplateViewSet / SlotBookingViewSet | 新建 |
| `backend/.../views/urls.py` | 注册 9 条路由 | 修改 |
| `backend/.../tests_slot_booking.py` | 模型/服务/API 三组测试 | 新建 |
| `backend/.../management/commands/seed.py` | 演示模板与抢占样例 | 修改 |
| `frontend/src/api/slotBooking.ts` | 全部接口封装 + TS 类型 | 新建 |
| `frontend/src/router/asyncRoutes.ts` | 两个一级菜单（rank 11/12） | 修改 |
| `frontend/src/views/slot-booking/index.vue` + `components/`（7 个） | 月历抢占页 | 新建 |
| `frontend/src/views/slot-config/index.vue` + 组件 | 配置页（模板管理/抢占记录两 Tab） | 新建 |

---

## Task 1: 后端模型层（两表 + 配置项 + 迁移）

**Files:**
- Create: `backend/build_protection_service/models/slot_booking.py`
- Modify: `backend/build_protection_service/models/__init__.py`
- Modify: `backend/config/settings.py`

- [ ] **Step 1: 创建 models/slot_booking.py**

字段与约束按设计文档 §4。核心骨架（字段补全后以此为准）：

```python
"""时段抢占领域模型：时间段模板 / 抢占记录。"""
from django.db import models
from django.db.models import Q


class SlotTemplate(models.Model):
    """时间段模板：管理员预配置的可抢占时段。"""

    name = models.CharField("时段名称", max_length=50, unique=True)
    start_time = models.TimeField("开始时间")
    end_time = models.TimeField("结束时间")
    weekdays = models.CharField("适用星期", max_length=20, blank=True, default="")
    effective_from = models.DateField("生效起始日", null=True, blank=True)
    effective_to = models.DateField("生效截止日", null=True, blank=True)
    color = models.CharField("标识色", max_length=20, default="#409eff")
    sort_order = models.IntegerField("排序", default=0)
    enabled = models.BooleanField("启用", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "时间段模板"
        verbose_name_plural = "时间段模板"
        ordering = ["sort_order", "id"]


class SlotBooking(models.Model):
    """抢占记录：date+template 唯一（仅 reserved），数据库层防并发双抢。"""

    STATUS_CHOICES = (
        ("reserved", "已抢占"),
        ("released", "已释放"),
        ("expired", "已过期"),
    )

    date = models.DateField("抢占日期")
    template = models.ForeignKey(
        "SlotTemplate", on_delete=models.PROTECT, related_name="bookings"
    )
    start_snapshot = models.TimeField("开始时间快照")
    end_snapshot = models.TimeField("结束时间快照")
    status = models.CharField("状态", max_length=10, choices=STATUS_CHOICES, default="reserved")
    user = models.ForeignKey("User", on_delete=models.PROTECT, related_name="slot_bookings")
    purpose = models.CharField("用途说明", max_length=200)
    version = models.ForeignKey("Version", on_delete=models.PROTECT, related_name="slot_bookings")
    branch = models.ForeignKey("Branch", on_delete=models.PROTECT, related_name="slot_bookings")
    created_at = models.DateTimeField("抢占时刻", auto_now_add=True)
    released_at = models.DateTimeField("释放时刻", null=True, blank=True)
    release_reason = models.CharField("释放原因", max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "时段抢占记录"
        verbose_name_plural = "时段抢占记录"
        ordering = ["date", "start_snapshot"]
        constraints = [
            models.UniqueConstraint(
                fields=["date", "template"],
                condition=Q(status="reserved"),
                name="uniq_slot_booking_active",
            )
        ]
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["user", "status"]),
        ]
```

- [ ] **Step 2: models/__init__.py 统一导出 + settings 加 SLOT_BOOKING_HORIZON_DAYS**
- [ ] **Step 3: 生成并执行迁移**（`python manage.py makemigrations build_protection_service && python manage.py migrate`；确认迁移文件包含 UniqueConstraint(condition=...)）
- [ ] **Step 4: 回归既有测试** `python manage.py test build_protection_service -v 1`，全部 PASS
- [ ] **Step 5: Commit** `feat: 时段抢占新增时间段模板与抢占记录数据模型`

---

## Task 2: 服务层（日历聚合 / 抢占事务 / 释放 / 重叠检测）

**Files:**
- Create: `backend/build_protection_service/services/slot_booking.py`
- Modify: `backend/build_protection_service/tests_slot_booking.py`（先写测试，TDD）

- [ ] **Step 1: 追加服务层测试到 tests_slot_booking.py**（夹具：admin/pm 用户 + 版本/分支 + 两个模板；用例清单见设计文档 §9，含：校验链各拒绝路径、IntegrityError→40904 语义函数返回、释放权限、日历 is_mine、惰性过期、月边界、重叠 warnings）
- [ ] **Step 2: 运行测试确认失败**（ModuleNotFoundError）
- [ ] **Step 3: 实现服务层**，函数签名：

```python
HORIZON_DAYS 来自 django.conf.settings.SLOT_BOOKING_HORIZON_DAYS

def build_slot_calendar(month: str, user) -> dict
    # "YYYY-MM" → {"month", "horizon_days", "templates", "days"}
    # 查询：启用模板一次 + 该月 reserved 记录一次（select_related user/version/branch）
    # 惰性过期：date < today 的记录按 expired 展示（不写库）
def create_booking(user, payload: dict) -> tuple[dict | None, dict | None]
    # 校验链 6 步（设计文档 §5.1）；返回 (booking_data, None) 或 (None, err_resp)
    # transaction.atomic + IntegrityError → (None, err(40904, f"该时段刚被 {占有人} 抢占"))
def release_booking(booking, actor, release_reason: str) -> dict | dict_err
    # 本人：reason 可选；admin 释他人：reason 必填（42201）；其余 40301
def detect_template_overlap(template: SlotTemplate) -> list[str]
    # 同星期下与其他启用模板区间重叠 → warnings 文案列表
```
- [ ] **Step 4: 运行服务层测试全部 PASS**
- [ ] **Step 5: Commit** `feat: 时段抢占服务层（日历聚合/抢占事务/释放/重叠检测）`

---

## Task 3: 序列化器

**Files:**
- Create: `backend/build_protection_service/serializers/slot_booking.py`

- [ ] **Step 1: SlotTemplateSerializer（name/start_time/end_time/weekdays/effective_from/effective_to/color/sort_order/enabled；validate: start_time < end_time 否则 42201 文案"不支持跨天时段，结束时间需晚于开始时间"）+ SlotBookingCreateSerializer（date/template_id/purpose/version_id/branch_id 全必填；validate: purpose 2~200 字、branch.version_id == version_id）**
- [ ] **Step 2: 导入冒烟** `python -c "from build_protection_service.serializers.slot_booking import SlotTemplateSerializer; print('ok')"`
- [ ] **Step 3: Commit** `feat: 时段抢占序列化器（跨天拦截与版本分支归属校验）`

---

## Task 4: 视图层 + 路由 + API 集成测试

**Files:**
- Create: `backend/build_protection_service/views/slot_booking.py`
- Modify: `backend/build_protection_service/views/urls.py`
- Modify: `backend/build_protection_service/tests_slot_booking.py`

- [ ] **Step 1: 创建视图**，两个 ViewSet（均 `permission_classes = [AllowAny]`，每 action 先 `authed_user`）：
  - `SlotTemplateViewSet`：list（全员）/ create / update / destroy（admin；destroy 时 `SlotBooking.exists()` → 40902"该时段已有抢占记录，请改用停用"）；create/update 返回 `{template, warnings}`。
  - `SlotBookingViewSet`：`create`（全员，调服务层）/ `@action release`（本人或 admin）/ `@action mine`（分页 20/100）/ `list`（admin，筛选 date_from/date_to/version_id/branch_id/user_id/status + 分页）。
  - 函数视图 `slot_calendar(request)`：`GET ?month=YYYY-MM` → `build_slot_calendar`。
- [ ] **Step 2: urls.py 注册 9 条路由**：`slot-templates`（GET/POST）、`slot-templates/<int:pk>`（PUT/DELETE）、`slot-calendar`（GET）、`slot-bookings`（GET/POST）、`slot-bookings/<int:pk>/release`（POST）、`slot-bookings/mine`（GET，注意注册顺序在 `<int:pk>` 之前或用独立 path）
- [ ] **Step 3: API 集成测试**（追加 tests_slot_booking.py）：未认证 40100、全角色抢占成功、各 42201 路径、并发双抢 40904、释放矩阵、admin 筛选列表、模板 CRUD 与删除拦截、非 admin 40301
- [ ] **Step 4: 全量回归** `python manage.py test build_protection_service -v 2` 全部 PASS
- [ ] **Step 5: Commit** `feat: 时段抢占视图层与路由注册（模板/日历/抢占/释放端点）`

---

## Task 5: seed 演示数据

**Files:**
- Modify: `backend/build_protection_service/management/commands/seed.py`

- [ ] **Step 1: 追加时段模板种子**（守卫锚点：`SlotTemplate.objects.filter(name="上午窗口").exists()` 跳过）：「上午窗口 08:00-12:00 工作日」「下午窗口 14:00-18:00 工作日」「夜间回归 19:00-22:00 全周」各配标识色与排序；为本月内 3 个工作日种 2~3 条 reserved 样例（version=27A/master，用途演示文案）
- [ ] **Step 2: 验证** `python manage.py seed` 幂等执行两次无重复
- [ ] **Step 3: Commit** `feat: seed 追加时段模板与抢占演示数据`

---

## Task 6: 前端 API 封装与类型

**Files:**
- Create: `frontend/src/api/slotBooking.ts`

- [ ] **Step 1: 封装 9 个接口**（走 `@/api/http`，参考 `branchConfig.ts` 风格）：getSlotTemplates / createSlotTemplate / updateSlotTemplate / deleteSlotTemplate / getSlotCalendar(month) / createBooking / releaseBooking / getMyBookings(page) / getSlotBookings(filters)；类型 SlotTemplateItem / BookingItem / CalendarDayCell / SlotCalendarResponse 内聚本文件
- [ ] **Step 2: 类型检查** `cd frontend && npx vue-tsc --noEmit` 无新增错误
- [ ] **Step 3: Commit** `feat: 前端时段抢占 API 封装与类型定义`

---

## Task 7: 前端菜单路由

**Files:**
- Modify: `frontend/src/router/asyncRoutes.ts`

- [ ] **Step 1: 追加两个一级菜单**（排在 branch-config 之后，rank 取文件现状最大值 +1/+2，暂定 11/12）：`/slot-booking`（SlotBooking，icon `ep/alarm-clock`，title「时段抢占」，roles ALL_ROLES）、`/slot-config`（SlotConfig，icon `ep/setting`，title「时段配置」，roles ADMIN_ROLE）
- [ ] **Step 2: 验证** dev 起服务，admin 见两菜单、普通角色只见「时段抢占」
- [ ] **Step 3: Commit** `feat: 新增时段抢占/时段配置一级菜单路由`

---

## Task 8: 月历抢占页

**Files:**
- Create: `frontend/src/views/slot-booking/index.vue`
- Create: `frontend/src/views/slot-booking/components/{MonthGrid,DayCell,SlotChip,BookingDialog,SlotDetailDialog,DayDetailDialog,MyBookingsDrawer}.vue`

- [ ] **Step 1: useSlotCalendar composable**（容器内实现即可）：month 状态 ↔ `route.query.month` 双向同步（深链/刷新保持）、load()（骨架屏/空态/错误态）、统计（本月总段/已占/我的）
- [ ] **Step 2: MonthGrid/DayCell/SlotChip**：42 格周对齐与补位、按设计文档 §7.2 渲染 8 状态芯片（颜色全走 Element Plus token；aria-label；`:focus-visible`；hover 上浮动效仅 transform/opacity）
- [ ] **Step 3: BookingDialog**：版本→分支级联必填（getPlan 数据源，切版本清空分支）+ purpose 2~200 计数；提交 loading；成功翻转芯片 + ElMessage；40904 时 ElMessage（拦截器已弹）+ 重拉当月
- [ ] **Step 4: SlotDetailDialog / DayDetailDialog / MyBookingsDrawer**：详情只读、释放（ElMessageBox 二次确认）、"+N"当日大卡、我的抢占抽屉列表与释放入口
- [ ] **Step 5: 交互验证**：抢占成功/并发失败/释放/月切换/空态五条主链路手测通过；<768px 降级为按天卡片列表
- [ ] **Step 6: Commit** `feat: 时段抢占月历页（月历/芯片/抢占弹窗/我的抢占抽屉）`

---

## Task 9: 时段配置页（admin）

**Files:**
- Create: `frontend/src/views/slot-config/index.vue` + 模板表单弹窗组件 + 记录筛选表格组件

- [ ] **Step 1: Tab 1 模板管理**：el-table 列表 + 新建/编辑弹窗（字段与校验按设计文档 §7.3；start<end 前端拦截"不支持跨天时段"；重叠 warnings 黄色告警条；删除二次确认，40902 提示改用停用）
- [ ] **Step 2: Tab 2 抢占记录**：筛选（日期范围/版本/分支/抢占人/状态）+ 分页表格 + admin 释放（必填原因弹窗）
- [ ] **Step 3: 验证**：模板 CRUD 全链路 + 记录筛选/分页 + 非 admin 直连 URL 进入被守卫拦截
- [ ] **Step 4: Commit** `feat: 时段配置管理页（模板管理/抢占记录两 Tab）`

---

## Task 10: 联调验证与回归

- [ ] **Step 1: 后端全量回归** `python manage.py test build_protection_service -v 2` 全部 PASS
- [ ] **Step 2: 前端** `npm run typecheck` 通过、`npm run lint:eslint` 无新增告警
- [ ] **Step 3: 双浏览器并发抢占实测**：A/B 同时抢同段，后提交方收到 40904 提示，且其日历自动刷新后该段显示为对方锁定
- [ ] **Step 4: 收尾**：设计文档 §9 测试计划逐项核对，遗留项记入本文件
