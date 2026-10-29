# 代码质量评估报告（2026-10-25，第七轮全量复评）

> 评估范围：`backend/`（Django 5 + DRF + SimpleJWT + SQLite，业务 app `build_protection_service`，业务代码约 4400 行 + 测试约 4500 行）与 `frontend/src`（Vue 3 + Vite + TS + Element Plus，pure-admin-thin v6.2.0，业务域 `views/panorama` + `views/strategy` + api/composables/utils/基座残留）。第六轮（2026-10-24，R6-B1~B16/R6-F1~F16）修复后的次日全量复评。
> 评估方法：后端通读 views/services/models/serializers/parsing/api/auth/errors/exception_handlers/admin/migrations/seed/settings，并交叉核对前端 `src/api` 对全部端点的真实消费关系与参数契约；前端通读 panorama/strategy 业务域全部源码 + api/utils/composables/router/store 全部业务文件，基座残留逐个 grep 引用核实（含动态 import）。四路并行深读（视图层/服务模型层/业务页面/基础设施）+ 主线逐条复核全部 P1/P2。
> 基线状态：后端 `python manage.py test build_protection_service` 全绿（325 例）；前端 `npm run test` 全绿（32 文件 264 例）；`makemigrations --check` 干净；`tsc`/`vue-tsc` 通过。
> 与前六轮的关系：第一轮约 5.5 分 → 第二轮 7 → 第三轮 7.5 → 第四轮 7.5 → 第五轮 8.0 → 第六轮后端 8.2/前端 8.3，本轮 **后端约 8.4 分、前端约 8.3 分**——核心写路径扎实（条件 UPDATE/唯一约束/IntegrityError 双格式匹配/seq 守卫/单一来源收敛在前六轮均已落地且无回退），本轮未发现安全漏洞与数据完整性 P0；问题呈两类：**①范式覆盖的「组件类型盲区」与「最后一个写入口」**（R6-F16 修复了三个 dialog 的挂载即开初始化，唯一 drawer 漏网；R6-B2 加固了 update_strategy 重读，toggle_strategy 仍是陈旧快照）；**②「规则演进、快照未跟上」的跨层契约漂移**（后端 R5-B10 回避规则前端权限包未跟上、identity 刷新与路由权限数据源脱节、40101 凭据错误被折叠进 40100 跳转）+ 一条六轮收敛时原样搬运的老 bug（parse_int 多负号）。

## 总体结论

本轮问题呈四个特征：

1. **范式覆盖的组件类型盲区**：R6-F16 固化了「弹窗初始化禁止只依赖 watch(modelValue) 或 @open」并修复了三个 el-dialog，但同一 `v-if` 挂载即开模式下唯一的 el-drawer（MyBookingsDrawer）漏网——element-plus useDialog 的 `@open` 只在非 immediate 的 modelValue watcher 里发出，挂载即开时永不触发，「我的抢占」抽屉恒空态、释放入口不可达（R7-F1，本轮唯一 P1）。
2. **最后一个写入口的并发死角**：`toggle_strategy` 校验仍用视图层事务外读出的陈旧快照（R6-B2 只修了 update）——并发 PATCH 改时间且停用态跳过校验后，toggle 用旧时间跑互斥/阶段校验再启用，新时间从未经过校验入库（R7-B2）；同族：admin 的 Version/Branch 以默认 ModelAdmin 注册（可删），删除版本/分支经 CASCADE 静默抹掉其下策略与进行中借用流——R4-B1/R6-B1 堵住的洞换了入口（R7-B3）。
3. **「规则演进、快照未跟上」的契约漂移**：后端 R5-B10 审批回避规则（借用人不得自批）落地后，前端 `canApproveBorrowFlow` 与其单测仍停在旧口径——自借单审批按钮可点、点了必 40301（R7-F4）；identity 启动刷新只写 pinia store，路由守卫与菜单过滤读的是基座 localStorage 的 roles，「免重登感知」声明与实现脱节（R7-F5）；前端把 40101（凭据错误）折叠进 40100（未认证）的跳转分支，密码输错零反馈且表单被整页重载清空（R7-F2）；plan.ts 声明后端并不消费的过滤参数、types.ts 声明后端并不返回的字段（R7-F14/F15）。
4. **小而实的老 bug 与死字段/死文件长尾**：`parse_int` 的 `lstrip("-")` 会剥掉全部前导负号，`?version_id=--5` 直接 500（六轮收敛 parsing.py 时原样搬运，R7-B1）；/plan 轮询热路径每次对全表启用策略跑子查询计算无任何前端消费方的 `status` 字段（R7-B4）；基座残留死文件/死依赖群（sso/globalPolyfills/localforage/tree 五函数/echarts 等，R7-F11/F12）。

**分级：P1 = 功能死角（可稳定复现），P2 = 并发缺口 / 契约漂移 / 热路径死计算，P3 = 死代码 / 注释漂移 / 工程卫生。** 编号规则：R7-Bx 后端、R7-Fx 前端、R7-Tx 测试基建；「处置」列标明本轮修复或记录在案。对应 spec：`specs/2026-10-25-code-quality-optimization-round7-design.md`，后端回归测试集中在 `tests_quality_round7.py`。

---

## 一、后端问题清单（backend/build_protection_service，简写 bps/）

### P2（中）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R7-B1 | **parse_int 多负号边界抛 ValueError → 500**：`text.lstrip("-")` 会剥掉全部前导负号（`"--5".lstrip("-")=="5"`），isdigit 守卫通过后 `int("--5")` 炸——本函数存在的意义就是避免 ValueError 500。所有把 query/body 原始参数交给 parse_int 的入口中招（`/api/strategies?version_id=--5`、`/api/weekly`、`/api/borrow-flows?page=--5`、`/api/slot-bookings/mine?page=--5` 等），应 42201 的参数错误全变 500；该实现自 views/services 双份时代就带病，六轮收敛 parsing.py 时原样搬运 | `bps/parsing.py:24`（实测 `"--5"` → ValueError） | 本轮修复：仅允许单个前导负号（`startswith("-")` 判定负号后其余段 isdigit），负零/多负号一律 None；回归测试覆盖 `--5`/`-5`/`+5`/全角 |
| R7-B2 | **toggle_strategy 校验用视图层陈旧快照，并发 PATCH 改时间后启用可绕过互斥/阶段校验**（R6-B2 在 update 修过的同款反模式）：视图事务外读出实例，toggle 的启用方向 `validate_strategy` 直接用 `strategy.build_start_time` 等旧值——他人 PATCH 把停用策略时间改到冲突点（停用态 check_conflicts=False 放行）后，toggle 按旧时间校验通过并条件 UPDATE 启用，新时间从未经过启用口径校验；条件 UPDATE 只钉住 enabled 字段，非 enabled 字段被并发修改时 rowcount 仍为 1，docstring「rowcount=0 说明…或字段被并发修改」与实现不符（夸大防线）。SQLite IMMEDIATE 救不了「实例读在事务外」；迁 PG 后该路径全程无 select_for_update | `bps/services/strategies.py:242-278` | 本轮修复：事务内 select_for_update 重读实例后再做校验与翻转（对齐 R6-B2 范式），返回重读实例；docstring 修正为「rowcount=0 仅说明 enabled 被并发翻转」；PATCH+toggle 交错回归测试 |
| R7-B3 | **admin 面板 Version/Branch 可删除，级联抹掉策略与进行中借用流**（R4-B1/R6-B1 堵住的洞换了入口）：Strategy.branch=CASCADE、BorrowFlow.strategy=CASCADE，admin 删分支（或删版本级联分支）静默抹掉其下全部策略、pending 借用流与 ExecutionRound 历史——R6-B12 只路由了 StrategyAdmin 的删除；SlotTemplate 删除被 SlotBooking PROTECT 挡住但 admin 直接抛裸 IntegrityError 错误页（防护有效、体验缺失） | `bps/admin.py:25-27,75-82,102` | 本轮修复：Version/Branch/StrategyTemplate 注册可管理但删除受限的 ModelAdmin——Version 有分支、Branch 有策略、StrategyTemplate 有策略引用时 delete_model 转 ValidationError 可读报错；SlotTemplate 删除把 PROTECT IntegrityError 转「存在抢占记录」可读提示 |
| R7-B4 | **/plan 轮询热路径每次对全表启用策略跑 ExecutionRound 子查询计算 `status` 字段，前端零消费**：panorama 数据中枢每次 refresh（轮询/切换/手动）都拉 /plan，响应里 status 无任何消费方（plan.ts 的 PlanStrategy 未声明、panorama/strategy 两页均不读）；全站唯一读者是 tests.py 的旧断言。页面精简删除结论/报告域后该字段成为死计算 | `bps/views/plan.py:50-64,101`（消费核对：`api/plan.ts`、`useScheduleData.ts:182-186`） | 本轮修复：删除 status_map 子查询与响应 status 字段；同步 tests.py 断言；panorama 设计文档补修订记录 |

### P3（低）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R7-B5 | **borrow_flow 两处口径残留**：① cancel 用 `refresh_from_db()` 后调 `_payload`——refresh_from_db 清空关联缓存，逐关联点查 5+ 次，与同文件 approve 路径的 R4-B14「重取 `_flow_qs()` 一次同时刷新标量与关联」范式相悖；② create 的 `except IntegrityError` 裸捕获不做消息匹配一律转 40903「已有待审批的借用申请」——并发删 target_branch 等非目标约束的 IntegrityError 也会返回误导性文案（R4-B8/R5-B2 在 slot_booking/strategies 两域已消除的同款过宽捕获，唯独借用发起漏网） | `bps/views/borrow_flow.py:181-182,300` | 本轮修复：cancel 改 `_flow_qs().get(pk)` 重取；IntegrityError 补 SQLite/PG 双格式消息匹配（uniq_pending_borrow_flow + borrower/strategy 组合），非匹配原样抛出 |
| R7-B6 | **变更日志漏记显式 null 清空**：`update_strategy` 对显式 `{"push_start_time": null}` 会真实清空字段（`push_start_time or None`），但 `_change_desc` 以 `body.get(field) is None` 跳过该字段——改名/改时间/启停都有「X: a→b」差异行，唯独清空推送时间这次真实变更在 StrategyChangeLog 里只剩「更新策略: X」，审计差异不完整 | `bps/services/strategies.py:153-160,227` | 本轮修复：`_change_desc` 改按「键在 body 中」判定参与留痕，显式 null 记「推送开始时间: X→（清空）」；回归测试锁定 |
| R7-B7 | **停用账号登录尝试零留痕**：密码正确但 is_active=False 直接 40301，既不写 security_log 也不计失败次数——login_failed/login_locked/login_success/logout 均有审计，唯独「凭据正确但被停用」这一探测型事件无痕；攻击者可无成本探测停用账号口令正确性 | `bps/views/login.py:73-74` | 本轮修复：补 `security_log("login_disabled", …)` 审计行（不计入失败限流——密码已验证正确，锁定语义针对爆破） |
| R7-B8 | **contract_exception_handler 兜底把 4xx APIException 归为 500**：else 分支对未枚举 APIException 一律 CODE_INTERNAL→HTTP 500——DRF 的 UnsupportedMediaType(415)/NotAcceptable(406) 等客户端错误混入服务端错误监控口径。全库现仅存 `SlotBookingViewSet`（create/mine/partial_update/release 四路由），415 路径经 `POST /slot-bookings` 传非 JSON Content-Type 实际可达——原稿「全库无 ViewSet、该 handler 实际不可达」为笔误（2026-10-30 复核修正），但兜底语义按 status_code 收敛成本极低 | `bps/exception_handlers.py:69-77` | 本轮修复：新增 UnsupportedMediaType/NotAcceptable → 42201；else 兜底按 `response.status_code < 500` 归 42201、否则 CODE_INTERNAL；单元测试直接喂异常实例锁定 |
| R7-B9 | **plan/weekly 的 `Version.objects.all()` 无显式排序**：模型无 Meta ordering，版本列表/甘特分组顺序依赖 DB 返回顺序（SQLite 恰好稳定，迁 Postgres 未定义）；同端点 branches/strategies 均显式排序 | `bps/views/plan.py:41-48`、`bps/views/weekly.py:36` | 本轮修复：两处补 `.order_by("id")`（版本 id 即创建序，稳定且与 seed 直觉一致） |
| R7-B10 | **seed.py 首块非幂等且无事务**：守卫锚点是 Version「27A」，块内 5 用户 + 2 版本 + 3 分支 + 2 模板 + 4 策略一气呵成——任一步中途失败（约束/磁盘异常）后 27A 仍未建，重跑必撞 username 唯一约束，seed 从此永久失败；其余段均已幂等化，唯独这段没有 | `bps/management/commands/seed.py:26-61` | 本轮修复：首块包 `transaction.atomic`（部分失败整体回滚，重跑干净）；回归测试模拟中途失败可重跑 |
| R7-B11 | **SlotTemplate「不支持跨天，强制 start < end」docstring 无任何实现**：模型无 CheckConstraint/clean，唯一写入口 SlotTemplateAdmin 与 seed 均不校验——admin 可建 22:00-06:00 逆序模板并正常抢占，start_snapshot/end_snapshot 与月历排序随之漂移 | `bps/models/slot_booking.py:12` | 本轮修复：模型补 CheckConstraint（start_time < end_time，migration 0017）+ SlotTemplateAdmin.save_model 前置校验（可读表单报错）；逆序模板回归测试 |
| R7-B12 | **注释漂移集群（第六轮改写后又产生的新漂移）**：① services/strategies.py update_strategy 注释「请求体未提供的字段不写列」与实现不符——update_fields 恒含 4 基础列 + updated_at，防丢更新实际由事务内重读保证而非 update_fields，后人据注释删掉重读将原样复活 R6-B2；② services/config.py「django-admin 可对 RuntimeConfig 手工建行生效」不实——RuntimeConfig 从未注册 admin，覆盖层无任何写入口（R6-B15 把旧的不实表述换成了新的不实表述）；③ views/slot_booking.py 模块 docstring「认证与错误码约定同 reports 模块」指向已删模块；④ views/admin.py 方法守卫排在认证+角色之后，与全站「方法守卫先行」顺序相反（builder 发 POST /admin/templates 得 40301 而非 42201） | `bps/services/strategies.py:220-222`、`bps/services/config.py:9`、`bps/views/slot_booking.py:3`、`bps/views/admin.py:20-28` | 本轮修复：①注释改为「防丢更新由事务内重读保证，update_fields 仅收窄写集」；②注册 RuntimeConfig 只读展示 ModelAdmin 使覆盖层可观测 + 注释如实描述单进程缓存边界；③docstring 改指 views/__init__ 约定；④方法守卫提到认证之前 |

---

## 二、前端问题清单（frontend/src）

### P1（高）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R7-F1 | **「我的抢占」抽屉挂载即开时初始化永不触发**（R6-F16 范式的组件类型盲区）：ScheduleDialogs 以 `v-if` 挂载 MyBookingsDrawer（点击入口即 modelValue=true），抽屉初始化只依赖 `el-drawer @open="load"`——element-plus useDialog（drawer 与 dialog 共用）的 `emit("open")` 只在非 immediate 的 modelValue watcher 里发出，挂载即开时永不触发：load() 不执行，抽屉恒显「暂无抢占记录」空态，释放/加载更多不可达。R6-F16 修复的三个 el-dialog 全部改了初始化方式，唯一 el-drawer 漏网 | `views/panorama/shared/MyBookingsDrawer.vue:7`、`shared/ScheduleDialogs.vue:42-46`（element-plus use-dialog.mjs:144 源码核实） | 本轮修复：补 `onMounted(() => { if (modelValue) load() })`（@open 保留兜底常规打开）；组件 spec 锁定挂载即开行为 |

### P2（中）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R7-F2 | **40101（凭据错误）被折叠进 40100 跳转分支**：拦截器 `code === 40100 \|\| code === 40101` 都执行 removeToken + 整页跳 /login（当前已在 /login，同 URL 赋值触发重载）——密码输错零反馈、表单被重载清空；登录页 catch 因 `isBizError(e)` 为真而抑制兜底提示（其注释假定「拦截器已对契约内错误弹提示」，对 40101 不成立）。errors.py 中 40100=未认证≠40101=凭据错误，两语义共用前端处理是契约漂移 | `api/http.ts:117-126`、`views/login/index.vue:69-76` | 本轮修复：仅 40100 走清理跳转；40101 归入常规错误分支弹「用户名或密码错误」toast；http.spec 补 40101 分支断言 |
| R7-F3 | **silent 后台轮询仍置 loading，S2~S5 每 30s 骨架闪烁**：refresh(silent) 无条件 `loading.value = true`，四布局 `el-skeleton v-if="loading"` 整体替换画布——每轮轮询请求在途全程（数百 ms）内容被骨架屏替换再复原：周期性闪烁、S4 分组卡整块卸载重建丢滚动位、BorrowApprovalDrawer 的 v-loading 每 30s 闪一次。refresh 注释宣称「后台轮询不打扰用户」只对 toast 生效 | `views/panorama/useScheduleData.ts:132,227`（s2-gantt:84 等 4 布局） | 本轮修复：loading 仅在非 silent refresh 置位/复位（silent 轮询不动 loading），数据照常更新；spec 断言 silent 轮询不改 loading |
| R7-F4 | **canApproveBorrowFlow 缺借用人回避分支，与后端 R5-B10 口径漂移**：后端 `_can_approve` 含 `borrower_id != user.id`（自借自批禁止，admin 亦不例外），前端仅判 role/bound_version_id，docstring 仍写「与后端 _can_approve 同口径」——PM/admin 查看自己发起的 pending 借用流时审批按钮可点，点击必 40301「不可审批自己发起的借用申请」；红点计数（panorama todos 已排除自借单）与按钮权限不一致。其单测全部用例只覆盖 role/bound_version 维度，「测试锁死旧语义」 | `utils/business.ts:42-50`、`utils/__tests__/business.spec.ts:139` | 本轮修复：补 `flow.borrower_id === user.id → false` 分支（后端 `_payload` 已返回 borrower_id，契约可支撑）；同步 business.spec 补回避用例；注释改写 |
| R7-F5 | **identity 刷新与路由/菜单权限数据源脱节**：refreshBusinessUser 只写 pinia store（SET_ROLES）+ 业务快照，而路由守卫（router/index.ts:141）与菜单过滤（router/utils.ts:81-91）读的是基座 user-info localStorage 的 roles，仅登录时写入一次——服务端改角色后菜单/路由仍按旧角色渲染直到重登；identity.ts 注释「角色用于菜单/路由权限过滤」与 App.vue「服务端变更后无需重新登录即可感知」均与事实不符 | `utils/identity.ts:22`、`router/index.ts:141`、`router/utils.ts:81-91` | 本轮修复：刷新成功后同步基座 user-info localStorage 的 roles 字段（storageLocal 原位更新），注释改写为如实描述；identity.spec 补同步断言 |
| R7-F6 | **S4「按状态」分组组名直出英文枚举**：keyOf 状态分支拼 `${source}\|${status}\|${statusText}`，而组名 `key.split("\|")[1]` 取到的是 `e.status`（"reserved"/"available"…）——违反「展示映射唯一来源 views/constants.ts（statusText）」范式；s4-board.spec 未覆盖按状态命名 | `layouts/s4-board/index.vue:211,220` | 本轮修复：状态分支 key 改以 statusText 命名（split 取段对齐），spec 补按状态分组命名断言 |

### P3（低）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R7-F7 | **策略事件 versionName 恒空串，S4「按版本」分组把同版本拆成两组**：WeeklyStrategy 契约无 version_name，事件 versionId 有值——key=`${versionId}\|${versionName\|\|"未关联版本"}` 下策略事件落 "5\|未关联版本"、同版本抢占落 "5\|V5.0"，两组同指一个版本（weeklyData.version.version_name 可得未透传） | `sources/strategySource.ts:110,171,193` | 本轮修复：数据中枢把当前版本名透传给 mapStrategyEvents，策略事件补 versionName；spec 补断言 |
| R7-F8 | **SlotDetailDialog 两条释放路径行为不一致 + 空壳弹窗**：① 无 booking 的 slot 事件（过期/超窗口的空闲时段）打开详情正文 v-if 全不渲染，只剩标题和关闭钮——应展示「空闲时段」提示；② 弹窗自身 handleRelease 成功后只 emit 不关闭，已释放记录以旧数据滞留屏上（总线 release() 路径则正确关闭） | `shared/SlotDetailDialog.vue:8,55-63,121-129` | 本轮修复：无 booking 时展示模板信息 + 「该时段暂无抢占记录」空态；自释放成功后 emit update:modelValue 关闭；组件 spec 补两条断言 |
| R7-F9 | **S2「仅看有任务分支」开关是永真无效过滤**：groupByBranch 只产出有事件的分组（count 恒 ≥1），filter 两态渲染完全相同——控件暗示关掉能看到空分支泳道，实际无实现，误导性死控件（spec 注释自认「永远非空」） | `layouts/s2-gantt/index.vue:180,201` | 本轮修复：删除开关与无效过滤；布局 spec 同步 |
| R7-F10 | **strategy 页与弹窗残留**：① `useRouter()` 死变量；② onMounted「从 URL query 读取编辑 id（F2 甘特跳转）」注释指涉已删的 weekly 甘特页（站内无任何 producer 推送 /strategy?id=）；③ StrategyBorrowDialog 未使用的 ElMessageBox 导入；④ 双入口校验口径残留——StrategyEditDialog 不 trim 策略名（纯空格放行）、不校验 build_start_time 非空（el-time-picker 清空后 payload 带 null 靠后端 42201 兜底），与 strategy 页三连校验差一环 | `views/strategy/index.vue:26,278-283`、`shared/StrategyBorrowDialog.vue:106`、`shared/StrategyEditDialog.vue:236-239` | 本轮修复：删死变量/死导入、注释改写；StrategyEditDialog 补 trim 与 build_start_time 必填校验对齐 strategy 页 |
| R7-F11 | **基座死文件/死导出清扫**（第六轮 R6-F14 清单的漏网批次，逐个 grep 核实零引用）：utils/sso.ts（唯一引用是被注释的 import）、utils/globalPolyfills.ts（无入口 import）、utils/localforage/ 整目录（连带 localforage 死依赖）、utils/tree.ts 6 导出中 5 个死（仅 buildHierarchyTree 被 router 用）、utils/message.ts closeAllMessage、store/modules/user.ts 两个「保持既有引用路径可用」re-export 垫片（注释声称的引用方不存在）、composables/useBranchColors.ts 的 branchColorMap（生产零消费）、views/panorama/selectors.ts 的 durationOf 再导出（仅测试引用）、borrowFormat.ts 的 formatFlowTime 别名（全仓无页面消费） | 各处 | 本轮修复：逐项删除（tree.ts 保留 buildHierarchyTree；branchColorMap 收敛为内部实现）；零引用死依赖 echarts/html2canvas-pro/@pureadmin/descriptions/vue-types 一并 uninstall（localforage 随目录删除） |
| R7-F12 | **工程卫生**：① tsconfig.json include 残留 `"mock/*.ts"`（mock 已删）；② .lintstagedrc JSON 条目 `--write--parser` 参数连写 typo（prettier 警告 unknown option，parser 声明失效）；③ package.json scripts 用 pnpm（`pnpm lint:eslint`）+ .husky/pre-commit 用 `pnpm exec lint-staged`，但仓库为 npm 生态（package-lock.json）——npm 环境下 pre-commit 钩子直接失败；④ router/modules/error.ts 的 `// showLink: false` 被注释，403/404/500 菜单组在侧边栏对所有角色可见（演示痕迹）；⑤ router/index.ts:157 roles 不满足时 `next({path})` 无 return（双 next，vue-router 4 控制台告警，pure-admin 上游同款问题） | `tsconfig.json:43`、`.lintstagedrc:8`、`package.json:22`、`.husky/pre-commit`、`router/modules/error.ts:9`、`router/index.ts:157` | 本轮修复：①删 include 残留；②修 typo；③scripts 与 husky 收敛为 npm；④showLink: false 恢复；⑤补 return |
| R7-F13 | **http.ts 拦截器三个前瞻护栏缺失**：① 成功拦截器对非信封 200 响应（blob/HTML 错误页/裸数组）`d.code` 为 undefined → 误入业务失败分支 reject BizError(-1) 并弹「请求失败」；② 请求取消（CanceledError）无 response → 落通用错误分支弹 toast；③ 并发多请求同时 401 时各自执行清理+跳转，无去重标志 | `api/http.ts:97,109,117` | 本轮修复：①非对象/无 code 字段响应原样透传（不误判失败）；②`axios.isCancel` 分流静默 reject；③401 跳转加 isRedirecting 去重标志；spec 三组用例锁定 |
| R7-F14 | **types.ts 幽灵字段与 null 口径**：① `StrategyItem.timeline/conflict` 注释「preview / strategies 返回」失实——/strategies 列表不返回 timeline（仅 preview/plan 返回），误导开发者直接吃 `strategy.timeline` 得 undefined；② `UserInfo.is_active` 后端 `_user_payload` 从不返回；③ `bound_version_id/bound_version_name` 后端可为 null 而类型未含 null | `api/types.ts:21,62` | 本轮修复：①注释改为「preview / plan 返回」；②删 is_active；③类型补 null |
| R7-F15 | **plan.ts 幽灵过滤参数 + weekly.ts 注释漂移**：① getPlan 声明 version_id/branch_id 过滤参数，后端 plan_view 只读 date，传入即被静默忽略，contract.spec 还在固化该无效参数（strategy 页被迫全量拉取后前端自筛）；② weekly.ts 注释「week_start 该周任一天，后端取默认周一」与后端行为不符——views/weekly.py 把传入日期直接作周首日连排 7 天，仅缺省时才取默认周一（当前前端恰好总传 mondayOf 才未暴露） | `api/plan.ts:40-48`、`api/weekly.ts:14` | 本轮修复：①删幽灵参数（后端 /plan 无过滤语义）+ contract.spec 同步；②注释改写为「须传周一（mondayOf），后端不归一化」；顺带补 weekly/slotBooking/borrowFlow 契约测试的 silent 透传断言（moduleContract 仅 panorama 有） |
| R7-F16 | **useScheduleData 用户快照单次捕获**：`getCurrentUser()` 在组合函数创建时读一次 localStorage，App.vue mounted 的 refreshBusinessUser 异步在后——首屏全景页的 mine/canApprove/canEdit 全用刷新前快照且轮询不重读（id 稳定仅角色类判定受影响，整页刷新后达成一致） | `views/panorama/useScheduleData.ts:95` | 记录在案（低危；完整修复需把 user 改为响应式来源，收益与改动面不成比例，待后端角色变更成为常态再议） |

---

## 三、测试基建（R7-Tx）

| 编号 | 内容 | 处置 |
|---|---|---|
| R7-T1 | 新增后端回归文件 `tests_quality_round7.py`（复用 Round4Fixture 共享夹具范式），覆盖 R7-B1~B11 行为锁定：parse_int 边界矩阵、toggle 并发交错（重读校验）、admin 删除拦截（Version/Branch/SlotTemplate）、plan 响应无 status、cancel 响应与 IntegrityError 匹配、变更日志 null 留痕、停用账号审计、异常归一、Version 排序、seed 中途失败重跑、SlotTemplate 逆序拦截 | 本轮落地 |
| R7-T2 | 前端补测试：MyBookingsDrawer 挂载即开、http.spec 40101 分支与三组前瞻护栏、useScheduleData silent 不动 loading、business.spec 回避分支、identity.spec 基座 roles 同步、s4 statusText 命名、strategySource versionName、SlotDetailDialog 空态与自释放关闭、StrategyEditDialog 必填校验；plan.ts 幽灵参数删除后 contract.spec 同步 | 本轮落地 |
| R7-T3 | 延续 R6-T3 结论：本轮 MyBookingsDrawer（P1）正是「组件 spec 从 stub 到真挂载」覆盖策略的产线——drawer 从未被组件级直测过（R6 报告既有覆盖缺口第 3 条），本轮补组件 spec 后挂载即开缺陷立即暴露；「新弹窗必须带组件 spec」范式扩展为「**新抽屉/浮层同样必须带组件 spec（含挂载即开用例）**」 | 本轮验证 |

### 既有测试覆盖缺口（本轮处置后仍记录在案的）

1. 基座 `utils/http` PureHttp 401 刷新链路（handRefreshToken/refreshTokenApi 调用后端不存在的 /refresh-token，属死链路但整体随基座保留，与 R7-F11 记录同批；后端无刷新端点是设计事实）。
2. `directives` 按钮级权限链（v-perms/v-auth 等五个指令 + ReAuth/RePerms 组件）业务零使用、登录写死 `permissions:["*:*:*"]` 使 hasPerms 恒 true——互为死重但属基座机制，本轮记录在案不删（删除涉及基座结构性收敛，待基座专项）。
3. LayoutSwitcher `?layout=` 深链 replace + localStorage 写入（R6 遗留，记录在案）。
4. settings 的 ALLOWED_HOSTS 缺省 `*` 与 FIRST_SUPERUSER_PASSWORD 缺省 "123456"——生产漏配 env 时防护强度与「安全默认值」注释承诺不对齐（SECRET_KEY 已强校验）。属部署清单项（第四轮已记录）；核实 `.env.example` 既有注释已覆盖提醒（ALLOWED_HOSTS 行注「生产必须配置实际域名，默认 * 仅用于本地开发」、超管行注「生产部署后立即改密」，均自初版 4a94043 即存在，本轮无需补充），不改运行时行为（改默认值会破坏本地零配置启动）。
5. stylelint 插件为幻影依赖（stylelint-scss/stylelint-order 等未显式声明，靠传递依赖解析）——需 npm install 更新 lock，随 R7-F12 记录，待依赖专项一并处理。

---

## 四、死代码 / 残留清单（本轮逐项 grep 核实）

| 对象 | 核实结论 |
|---|---|
| 后端 views/slot_booking.py `ValidationError` import | 死 import（模板 CRUD 下线残留，R7-B12 同批删除） |
| 后端 RuntimeConfig | 机制保留（覆盖层预留），本轮注册 admin 使注释成真 |
| 前端 sso.ts / globalPolyfills.ts / localforage/ / tree.ts 5 函数 / message.closeAllMessage / store 双垫片 | 零引用死代码，R7-F11 删除 |
| 前端 dead deps：echarts、html2canvas-pro、@pureadmin/descriptions、vue-types | src 零引用（echarts 仅 types/global.d.ts 与 build/cdn.ts 残留），R7-F11 uninstall |
| 前端 refreshTokenApi / PureHttp 401 刷新队列 | 死链路（后端无 /refresh-token），随基座保留记录在案 |
| 前端 directives 权限链 | 业务零使用（仅 v-ripple 一处在用），基座机制保留记录在案 |
| router remaining.ts 的 /access-denied、/server-error 全屏路由 | 全仓零引用，R7-F11 删除 |
| 前端 api/*.ts 全部导出 | 逐一 grep 均有生产消费，无死导出（plan.ts 幽灵参数为参数级非导出级） |

---

## 五、做得好的方面

- **前六轮修复零回退**：条件 UPDATE 抢占、IntegrityError 双格式匹配、字段级非 str 拒绝、check_str_len、seq 双守卫、单一来源收敛（查询 mutator/展示映射/周一计算/formatDateTime/剪贴板）、弹窗成功回触等既有范式在全部存量代码中落实到位。
- **迁移链健康**：0001→0016 与当前模型逐字段比对一致，三个部分唯一约束名正确，0015 手写 RemoveConstraint 前置顺序正确，`makemigrations --check` 干净。
- **视图层纪律扎实**：方法守卫/manual auth/parse_int/body_str 全覆盖、列表端点 select_related 零 N+1、PM fail-closed 空集、panorama 排除自借单，17 个端点前后端契约逐字段吻合（唯 plan.ts 幽灵参数一处参数级漂移）。
- **权限位与后端口径基本对齐**：canEditPanorama↔_check_pm_bound、canReleaseOthers↔非 owner 必填原因、canReschedule↔改期条件，路由 roles 与菜单语义一致（唯 R7-F4 回避分支一处漂移）。
- **HTTP 层主体健壮**：无 `catch (e: any)`、silent 使用精准、401 跳转统一走 appHashUrl（唯 40101 折叠与三个前瞻护栏缺口）。
- **安全默认姿态**：生产缺 SECRET_KEY 拒绝启动、DEBUG/CORS 默认收紧、登录限流 add+incr 原子固定窗口、CSRF 仅保护 admin 面。

**总体判断**：本轮后端约 8.4 分、前端约 8.3 分——六轮治理后主链路无结构性问题，剩余问题集中在「范式覆盖盲区（drawer/toggle/admin 级联）」与「规则演进的跨层契约漂移（回避规则/身份刷新/40101）」两类，均为小改可清。修复 R7-B1~B12 与 R7-F1~F15 后可到 8.7 一线；剩余长尾为基座残留（directives/PureHttp 刷新链）与部署清单项，建议另行专项。
