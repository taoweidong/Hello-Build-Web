# 第七轮代码质量优化方案（2026-10-25）

> 对应评估报告：`docs/code-quality-assessment-2026-10-25.md`（R7-B1~B12 / R7-F1~F15）。
> 主题：**范式覆盖盲区（drawer 挂载即开 / toggle 陈旧快照 / admin 级联）与「规则演进、快照未跟上」的跨层契约漂移（审批回避 / 身份刷新 / 40101）**，附带 parse_int 老 bug、/plan 死字段与基座死文件长尾清扫。
> 基线：后端 325 例全绿；前端 264 例全绿；本轮新增后端回归 `tests_quality_round7.py`，前端回归随各 spec 文件扩展。

## 设计原则（延续前六轮）

1. **拒绝优于静默**：parse_int 多负号、SlotTemplate 逆序——非法输入一律拒绝（42201 / admin 表单报错），不做静默修正。
2. **条件 UPDATE + 事务内重读**：toggle_strategy 与 update_strategy 同标准——事务内 select_for_update 重读实例，校验与翻转基于最新状态；返回值供视图组装响应。
3. **写入口全收敛**：admin 面板任何可删除模型必须核对级联面（Version→Branch→Strategy→BorrowFlow），有业务引用的根实体删除一律拦截并给可读文案。
4. **契约漂移以「后端为准」回改前端**：审批回避（R5-B10）、weekly 周首日语义、/plan 无过滤语义、40101≠40100——前端权限包/注释/类型向后对齐，不改后端既定行为。
5. **挂载即开初始化范式扩展到浮层全类型**：dialog 已固化（R6-F16），drawer 同款——`onMounted` 判 modelValue + 保留 @open 兜底。
6. **死代码连同其单测一起删**（第五轮固化的清扫纪律第七次执行）。

## 后端改动（R7-B）

### R7-B1 parse_int 多负号（P2）
`parsing.py`：str 分支改写——先 strip；若以 `-` 开头则去掉**一个**负号后要求剩余段非空且 `isascii()+isdigit()`；`--5`/`- 5`/`+5`/空串/全角一律 None；`-5` → -5、`-0` → 0。docstring 补边界说明。

### R7-B2 toggle_strategy 事务内重读（P2）
`services/strategies.py toggle_strategy`：函数体开头 `Strategy.objects.select_for_update().select_related(...).get(pk=strategy.pk)` 重读（对齐 update_strategy R6-B2），校验与条件 UPDATE 均基于重读实例；返回重读实例。docstring 修正 rowcount 语义（仅说明 enabled 被并发翻转）。视图层无需改（已用返回值组装响应？——核对 views/strategies.py toggle 分支，若用旧实例需改用返回值）。

### R7-B3 admin 删除面收敛（P2）
`admin.py`：
- `VersionAdmin.delete_model`：存在关联 Branch 时抛 ValidationError「版本下存在分支，禁止删除」；`delete_queryset` 逐条同款。
- `BranchAdmin`（新注册，list_display name/version/enabled）：存在 Strategy 时抛 ValidationError「分支下存在策略，禁止删除」。
- `StrategyTemplateAdmin`（新注册，list_display）：被 Strategy 引用时抛 ValidationError。
- `SlotTemplateAdmin.delete_model`：捕获 PROTECT IntegrityError 转 ValidationError「该时段已存在抢占记录，禁止删除（可停用）」。
- Level：全部转 Django admin 可读错误页，不阻断列表。

### R7-B4 /plan 删除 status 死字段（P2）
`views/plan.py`：删 `latest_round` 子查询、`status_map` 与响应 `status` 键；`tests.py` 相应断言改「响应无 status 字段」或直接删除该断言部分；panorama 设计文档补修订记录（/plan 契约变化：字段删除属向后兼容裁剪，前端从未消费）。

### R7-B5 borrow_flow 收口（P3）
- cancel：`flow.refresh_from_db()` 改 `flow = _flow_qs().get(pk=flow.id)`（对齐 approve R4-B14 注释口径）。
- create：`except IntegrityError` 补双格式消息匹配（`uniq_pending_borrow_flow` 或 `borrow_flow` + `strategy_id` + `status` 字段组合）——匹配命中转 40903，未命中 `raise`。

### R7-B6 变更日志 null 留痕（P3）
`_change_desc(old, body)`：判定从 `body.get(field) is None → skip` 改为 `field not in body → skip`；`new_val = body.get(field)`；push_start_time 的 falsy（None/""）统一记 `→（清空）`。展示格式：`推送开始时间: 20:00→（清空）`。enabled 为 bool 不受影响；name/push_mode 正常。注意：body 中值与非空 str 的既有行为不变。

### R7-B7 停用账号审计（P3）
`views/login.py`：`if not user.is_active:` 分支补 `security_log("login_disabled", username=username, request=request)`。不计失败限流（注释说明语义差异）。

### R7-B8 exception handler 4xx 归一（P3）
`exception_handlers.py`：import `UnsupportedMediaType, NotAcceptable`；新增分支 → CODE_UNPROCESSABLE；else 兜底改 `code = CODE_UNPROCESSABLE if response.status_code < 500 else CODE_INTERNAL`。

### R7-B9 Version 显式排序（P3）
`views/plan.py` 与 `views/weekly.py`：版本 qs 补 `.order_by("id")`。

### R7-B10 seed 首块事务化（P3）
`seed.py`：`if not Version.objects.filter(name="27A").exists():` 块整体包 `with transaction.atomic():`。

### R7-B11 SlotTemplate start<end 不变量（P3）
`models/slot_booking.py`：SlotTemplate.Meta.constraints 补 `CheckConstraint(condition=Q(start_time__lt=F("end_time")), name="slot_template_start_lt_end")`（需 import F）；`makemigrations` 生成 0017。`admin.py SlotTemplateAdmin.save_model`：`obj.start_time >= obj.end_time` 时抛 ValidationError「开始时间必须早于结束时间（不支持跨天）」。

### R7-B12 注释漂移与方法守卫顺序（P3）
- `services/strategies.py:220-222`：注释改为「防丢更新由事务内重读保证；update_fields 收窄写集（updated_at 须显式列入）」。
- `services/config.py`：docstring 改为如实描述——覆盖层当前无写入口（RuntimeConfig 已注册 admin 只读展示，如需写入口须显式开通）；缓存为进程内，多进程部署不共享。
- `admin.py`：注册 `RuntimeConfigAdmin`（只读 list_display key/value）。
- `views/slot_booking.py:3` docstring：改「认证与错误码约定同 views/__init__（统一响应契约）」。
- `views/admin.py templates_view`：方法守卫移到 authed_user 之前。
- 删除 `views/slot_booking.py` 死 import ValidationError。

## 前端改动（R7-F）

### R7-F1 MyBookingsDrawer 挂载即开（P1）
`MyBookingsDrawer.vue`：`onMounted(() => { if (props.modelValue) load(); })`（props 需先接住 defineProps 返回值）；`@open` 保留兜底。组件 spec：mount with modelValue=true → getMyBookings 被调用（补进 `__tests__/MyBookingsDrawer.spec.ts`）。

### R7-F2 40101 不跳转（P2）
`api/http.ts`：分支拆开——仅 `code === 40100` 执行清理+跳转；40101 落入下方常规错误分支（非 silent 弹 toast「用户名或密码错误」）。http.spec：40101 不触发 location.href、弹 toast；40100 保持跳转。

### R7-F3 silent 轮询不动 loading（P2）
`useScheduleData.ts refresh`：`loading.value = true` 仅 `if (!silent)`；finally 段复位同样仅 `if (!silent && current === seq)`。注意首个 weekly await 后的「版本变化触发 watcher 二次拉取」路径不受影响。spec：silent=true 调用期间 loading 恒 false（mock 延迟响应断言）。

### R7-F4 canApproveBorrowFlow 回避分支（P2）
`utils/business.ts`：签名扩展 flow 参数为 `{ source_version_id: number; borrower_id: number }`；`if (user && flow.borrower_id === user.id) return false;` 置于 role 判定前（admin 亦回避）。调用方 `sources/borrowSource.ts` 传入 borrower_id（BorrowFlowItem 已含）。business.spec 补三例：admin 自借单 false、pm 自借单 false、他人单不受影响；注释同步。

### R7-F5 identity 同步基座 roles（P2）
`utils/identity.ts`：刷新成功后 `storageLocal().setItem(userKey, {...原对象, roles: [user.role]})`（读原值避免覆盖 username/expires）；无原值则跳过（未登录态）。注释改写；identity.spec 补断言：刷新后基座 user-info.roles 更新。

### R7-F6 S4 状态分组命名（P2）
`layouts/s4-board/index.vue`：keyOf 状态分支改为 `${e.source}|${e.statusText}`（key 语义即组名，statusText 来自 constants 唯一来源）；折叠/组名逻辑不变。spec：按状态分组时组名为中文文案。

### R7-F7 策略事件 versionName 透传（P3）
`useScheduleData.ts`：`mapStrategyEvents({ ..., versionName: weeklyData.version?.version_name ?? "" })`；`sources/strategySource.ts` 策略事件写 `versionName: versionName ?? ""`（借用/slot 事件不变）。spec 断言。

### R7-F8 SlotDetailDialog 空态与自释放关闭（P3）
模板：`v-if="template && entry?.booking"` 的正文外加 `v-else` 空态块「该时段暂无抢占记录」+ 模板信息行；`handleRelease` 成功后 `emit("update:modelValue", false)`。组件 spec 补两例。

### R7-F9 S2 无效开关删除（P3）
`layouts/s2-gantt/index.vue`：删 onlyBusy ref、开关 UI、filter；spec 删对应用例（注释「永远非空」的用例一并删）。

### R7-F10 strategy 页/弹窗残留（P3）
- `views/strategy/index.vue`：删 `const router = useRouter()`（含 import 若无他用）；注释「F2 甘特跳转」改写为现役入口描述。
- `StrategyBorrowDialog.vue`：删 ElMessageBox 死导入。
- `StrategyEditDialog.vue`：onSave 补 `form.name.trim()` 校验（纯空格 422 前置）与 build_start_time 必填校验（对齐 strategy 页三连）。spec 补断言。

### R7-F11 基座死文件清扫（P3）
删除：`utils/sso.ts`、`utils/globalPolyfills.ts`、`utils/localforage/`、`utils/tree.ts` 的 extractPathList/deleteChildren/getNodeByUniqueId/appendFieldByUniqueId/handleTree（保留 buildHierarchyTree）、`utils/message.ts` 的 closeAllMessage、`store/modules/user.ts` 的 `tokenExpiresAt`/`businessUserKey` re-export 垫片（import 改直连）、`useBranchColors.ts` 的 branchColorMap 导出（收敛为模块内实现）、`selectors.ts` 的 durationOf 再导出（spec 直连源 import）、`borrowFormat.ts` 的 formatFlowTime 别名（改内部函数名直接用 formatDateTime）、`router/modules/remaining.ts` 的 /access-denied、/server-error 两条零引用路由、`types/global.d.ts` 的 echarts 类型残留与 `build/cdn.ts` echarts 条目、`build/optimize.ts` vue-types 条目。uninstall 死依赖：echarts、html2canvas-pro、@pureadmin/descriptions、vue-types（localforage 随目录删）。每项删除前 grep 复核。

### R7-F12 工程卫生（P3）
- tsconfig.json include 删 `"mock/*.ts"`。
- .lintstagedrc `--write--parser` → `--write --parser`。
- package.json scripts：`pnpm lint:eslint` → `npm run lint:eslint`（其余 pnpm 调用同步）；clean:cache 删 pnpm-lock 残留改为 npm 口径。
- .husky/pre-commit：`pnpm exec lint-staged` → `npx lint-staged`。
- router/modules/error.ts：恢复 `showLink: false`。
- router/index.ts 403 分支补 `return`。

### R7-F13 http.ts 前瞻护栏（P3）
- 成功拦截器：`typeof d === "object" && d !== null && "code" in d` 才走信封判定，否则原样返回 res.data（防 blob/HTML 误判失败）。
- 错误拦截器：`axios.isCancel(err)`（或 `err?.code === "ERR_CANCELED"`）→ 静默 reject `BizError(-1, "请求已取消")` 不弹 toast。
- 401 分支：模块级 `let redirectingToLogin = false`；已置位则直接 reject（不重复清理/赋值 location）。
- http.spec 三组用例。

### R7-F14 types.ts 修正（P3）
- StrategyItem.timeline 注释改「preview / plan 返回」。
- UserInfo 删 is_active；bound_version_id/bound_version_name 补 `| null`。
- 全仓编译受影响处排查（getCurrentUser 消费方对 null 的兼容）。

### R7-F15 plan.ts 幽灵参数与注释（P3）
- getPlan params 收敛为 `{ date: string }`；contract.spec 同步。
- weekly.ts 注释改「须传该周周一（mondayOf），后端不归一化」。
- moduleContract.spec 补 weekly/slotBooking/borrowFlow 的 silent 透传断言。

## 测试与验证门禁

1. 后端每批修复后：`cd backend && python manage.py test build_protection_service`（325+新增全绿）。
2. 前端每批修复后：`npm run test` + `npm run typecheck`；业务代码改动 `npx eslint "src/"` 全清；构建产物相关批次 `npm run build`。
3. 迁移：R7-B11 生成 migration 0017，`makemigrations --check` 干净。
4. 提交拆分：①后端修复 + 回归测试；②前端修复 + 回归测试；③文档同步（报告/spec/plan/AGENTS/README/设计文档修订）。每次提交前重跑对应门禁（AGENTS.md 纪律）。

## 风险与回退

- R7-B2 toggle 重读：SQLite 测试库 FOR UPDATE 为 no-op，靠 IMMEDIATE 语义；现有 tests_strategy_concurrency 的 toggle 用例需全部通过。
- R7-B11 CheckConstraint：生产库若已存在逆序模板会迁移失败——评估为极低概率（模板仅 seed/admin 写入且 seed 数据合法），迁移文件不做数据修复前置。
- R7-F2：既有 http.spec 中「40101 跳转」断言（如有）需反转为「不跳转」。
- R7-F11/F12：删除均为零引用对象，构建与测试是完整回归门禁。
