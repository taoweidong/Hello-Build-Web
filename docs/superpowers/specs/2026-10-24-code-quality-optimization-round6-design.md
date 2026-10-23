# 第六轮代码质量优化设计（2026-10-24）

> 对应评估报告：`docs/code-quality-assessment-2026-10-24.md`（R6-B1~B16 / R6-F1~F15 / R6-T1~T2）。
> 主题：**页面精简后残留专项**——精简「只删不管」的运维缺口、五轮范式在 create/update 最后两个写入口的死角、「死代码 + 锁定其单测」回潮清理。
> 纪律：每批改动后必须跑 `python manage.py test build_protection_service` / `npm run test`（+typecheck/build），全绿才允许提交。

## 1. 后端设计决策（R6-Bx）

### R6-B1 时段模板管理入口恢复（含 admin 面板整体收敛）

- `admin.py` 注册 `SlotTemplateAdmin`（list_display: name/start_time 不便直显——直接 name/weekdays/enabled/sort_order，可增删改：模板写入面唯一合法入口即 django-admin + seed，与 views/slot_booking.py docstring 对齐）。
- 新增 `_ReadOnlyAdmin`（has_add/change/delete_permission 全 False），`SlotBooking`、`BorrowFlow`、`SecurityLog`、`AdminOpLog`、`StrategyChangeLog` 全部走只读注册（R6-B12 一并落地：审计不可篡改）。
- `StrategyAdmin` 补 `delete_model` / `delete_queryset`：路由到共享 `services.strategies.delete_strategy`，pending 借用流拦截在 admin 面板同样生效（R4-B1 最后缺口）。删除被 40903 拦截时转 `ValidationError` 让 admin 报错页可读。

### R6-B2 update_strategy 并发加固

- 服务内 `transaction.atomic` 已有；进入后先 `Strategy.objects.select_for_update().select_related("branch__version", "branch", "template").get(pk=strategy.pk)` 重读（SQLite 上 FOR UPDATE 为 no-op，靠 IMMEDIATE 串行；PG 上是真行锁——迁 PG 后这层是主要防线）。
- `old = strategy_payload(fresh)` 以重读后实例为基准（变更日志 diff 才反映真实旧值）。
- 字段合并后 `save(update_fields=[...])`：恒含 build_start_time/push_start_time/push_mode/enabled/updated_at；仅当 body 提供 name 时含 name。杜绝陈旧快照回写未请求字段。
- **配套接线（实施期既有 3 例断言失败暴露）**：服务层重读后返回的是新实例，`views/strategies.py` 必须用返回值组装响应（`s = svc_update(...)`）——沿用外层陈旧实例会把未落库的旧字段回给前端。范式：**服务层一旦重读实例，调用方必须改用返回值**。

### R6-B3 create_strategy 口径

- `validate_strategy(..., check_conflicts=enabled)`——与 update/toggle 对齐「仅结果态为启用才跑冲突校验」。DB 部分唯一约束本来就只约束 enabled=True，停用创建不需要 DB 之外的拦截。

### R6-B4 抢占 purpose 双路径口径统一

- 服务层 `create_booking`：`raw = payload.get("purpose")`，非 str（含 None）→ 42201「purpose 应为字符串」（与 reschedule 的 R5-B9 文案一致）；str 则 strip 后走既有 2~200 校验。
- 序列化器：新增 `StrictCharField(CharField)`——`to_internal_value` 对非 `str` 直接 `self.fail("invalid")`（错误消息「purpose 应为字符串」），杜绝 API 路径 int→str 静默强转；`ReleaseBookingSerializer.release_reason` 同款严格化（错误消息「释放原因应为字符串」）。
- 注意既有测试若断言「缺 purpose → 用途说明需 2~200 字」需按新口径调整（缺 purpose 现为「purpose 应为字符串」，语义同为 42201）。

### R6-B5 release_booking 服务层 reason 守卫

- 非 str → 42201「释放原因应为字符串」；strip 后 len > `SlotBooking.release_reason.max_length`（200）→ 42201「释放原因长度不能超过 200 字符」。None 归一为 ""（沿用「本人释放原因可选」语义）。

### R6-B6 BorrowFlow.borrower → PROTECT

- 出 migration 0016（AlterField）。删除有借用记录的用户 → ProtectedError（django-admin 报错页可读，与 approver/target_branch 同款行为）。审计链发起方强存活。

### R6-B7 借用 reason 拒绝优于截断

- `views/borrow_flow.py` create：`reason = body_str(body, "reason")` 后 `check_str_len(reason, "借用原因", 500)`（TextField 无模型上限，500 为既有 UI/接口口径的业务上限，超出 42201）。check_str_len 由此获得真实生产调用点（R6-B13）。

### R6-B8 panorama todos 排除自借单

- admin 分支 `pending.exclude(borrower=user).count()`；pm 分支 filter 后 `.exclude(borrower=user)`。口径注释更新为「与 _can_approve 完全同源（含 R5-B10 回避规则）」。

### R6-B9 logout 审计条件化

- 仅当 `username` 非空（token 有效且解析出用户）才 `security_log("logout", ...)`；响应契约不变（无 token 仍 200 ok）。既有固化相反行为的测试断言同步更新。

### R6-B10 客户端 IP 唯一来源

- `views/__init__.client_ip(request)`：`REMOTE_ADDR` 优先，回退 XFF 首段 strip。`security_log` 与 `views/login._client_ip`（删除本地副本改 import）统一走它。

### R6-B11 全角月份硬化

- `build_slot_calendar` 解析后对 year/mon 段加 `isascii() and isdigit()` 前置（`int("２０２６")` 合法是既有陷阱），非法 → 既有 42201「月份格式非法」。

### R6-B13~B15 清理

- 删 `require_admin`；`check_str_len` 保留（R6-B7 接线）。删 `filters/` 目录与 settings 两处 django_filters 配置。注释集群按精简后事实改写（strategies 模块头/create/toggle/delete 的入口描述、errors.py 40903、serializers/__init__.py docstring、services/config.py RuntimeConfig、views/plan.py annotate 注释）。

## 2. 前端设计决策（R6-Fx）

### R6-F1 释放能力位接线

- `eventActions.buildEventActions`：释放项条件改 `e.permissions.canRelease || e.permissions.canReleaseOthers`（二者互斥），label/type/run 不变——`useScheduleActions.release` 内部已按 isMine/others 分流（他人必须 prompt 原因），无需新动作。

### R6-F2 布局解构瘦身

- 五布局逐个只保留真实消费的字段（以模板内引用为准逐变量核对）。装配总线的「扁平铺开」契约不变（其他字段仍可按需取用）。

### R6-F4 死纯函数清理

- 删 `week.ts` 的 `isoWeek`/`buildMonthWeeks`、`slotCalendar.ts` 的 `summarizeCalendar` 及 week.spec/slotCalendar.spec 对应 describe；`mondayOf`/`buildDateRange`/`WEEKDAY_CN_*`/`buildMonthCells` 存活保留。

### R6-F5/F6 动作路径一致性

- BookingDialog 成功路径补 `emit("update:modelValue", false)`。
- `useScheduleActions` 增加 `batchReleasing` ref：releaseBatch 入口置 true / finally 复位；S4 批量按钮 `:loading="actions.batchReleasing"`。

### R6-F7 策略页表单校验

- onSave 前置三连校验（对齐 StrategyEditDialog）：名称非空（≤200）、build_start_time 合法 HH:MM、branch_id>0 且 branchOptions 含该分支；不通过 ElMessage.warning 并中止。onMounted 的降级判定改判 branchOptions（修正 templateOptions 口径错位）。

### R6-F8 past slot 详情放行

- S2/S3 的事件点击处理器：`isPastSlot(...)` 分支不再拦截 `openDetail`（详情恒可看），仅操作类仍受限；与 S4/S5「详情」恒可用口径对齐。

### R6-F9/F10/R6-T2 测试补全

- moduleContract.spec 补 `getPanoramaTodos`（URL/静默参数断言）。
- 新增 `SlotDetailDialog.spec.ts`（释放确认流转、:loading、失败保留弹窗）、`BookingDialog.spec.ts`（必填校验、超窗口拦截、成功 emit booked 且关闭弹窗）。
- eventActions.spec 补 canReleaseOthers 用例；s4 spec 补批量在途守卫断言；s2/s3 spec 补 past 详情放行断言。

### R6-F11~F15 清理与小修

- 注释漂移一次性改写（useScheduleData/useScheduleActions/useStrategyPreview/useBranchColors/borrowFormat/StrategyBorrowDialog/s3/helpers/constants/slotSource）。
- appUrl.spec 样例换现役路由。
- slotTruncated 注释标注触发条件（预留自定义范围场景）。
- R6-F14：grep 复核零引用后删 plugins/echarts.ts、components/RePureTableBar/、components/ReCol/、utils/print.ts、utils/preventDefault.ts、utils/propTypes.ts、api/user.ts#getLogin（有任一引用则保留并记录）。
- strategySource 入参改 `Role`（或 isRole 收窄）；strategy 页 onMounted `Promise.all` 并行、loadMeta 内两请求并行。

### R6-F16 「挂载即开」弹窗初始化（实施期由 R6-F10 新增组件测试实证发现）

- 病灶：ScheduleDialogs 以 `v-if` 挂载弹窗（挂载即 modelValue=true），`watch(modelValue)`（无 immediate）与 el-dialog `@open` 在该挂载方式下永不触发——编辑弹窗不回填、抢占弹窗不拉 /plan、借用弹窗不拉目标版本列表。
- 修复：StrategyEditDialog/BookingDialog 的 watch 补 `immediate: true`（回调内保留 `if (!visible) return` 守卫，兼容常驻挂载 + v-model 切换的旧用法）；StrategyBorrowDialog 补 `onMounted(() => { if (modelValue) onOpen() })`（onOpen 幂等：planVersions 非空即跳过）。
- 范式固化（入质量清单）：**弹窗初始化禁止只依赖 `watch(modelValue)` 或 `@open`——凡可能被 v-if「挂载即开」使用的弹窗，初始化必须同时覆盖挂载态（watch immediate / onMounted 判 modelValue）**；新弹窗必须带组件 spec（挂载即开 + v-model 切换两种口径）。

## 3. 风险与兼容

- R6-B2/B3 行为变化属「修正误拦/丢更新」，不破坏既有合法调用；round5 的 update 相关测试（停用改名放行等）必须继续全绿——update_fields 只影响写列集，语义不变。
- R6-B4 缺 purpose 报错文案从「用途说明需 2~200 字」变为「purpose 应为字符串」（仅服务层直调路径），API 路径缺参仍由序列化器「必填字段」拦截——round2 既有测试按新口径微调。
- R6-B6 出 migration，`makemigrations --check` 必须保持干净。
- R6-F1/F8 是行为增强；S4/S5 与 S2/S3 详情口径统一后，布局 spec 的既有断言需逐条核对。
