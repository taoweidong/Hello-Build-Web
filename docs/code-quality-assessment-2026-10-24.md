# 代码质量评估报告（2026-10-24，第六轮——页面精简后残留专项）

> 评估范围：`backend/`（Django 5 + DRF + SimpleJWT + SQLite，业务 app `build_protection_service`，业务代码约 4400 行 + 测试约 4400 行）与 `frontend/src`（Vue 3 + Vite + TS + Element Plus，pure-admin-thin v6.2.0，业务域 `views/panorama` + `views/strategy` + api/composables/utils）。2026-10-20 页面精简（HEAD=b37bab6，删除 2.4 万行、全站收敛为「调度全景 + 策略配置」两个业务页）之后的首次全量复评。
> 评估方法：后端全量通读 views/services/models/serializers/parsing/api/auth/errors/exception_handlers/admin/migrations/seed/settings，并交叉核对前端 `src/api` 对全部端点的真实消费关系；前端通读全部业务源码并对每条死代码结论逐一 grep 引用核实（含动态 import 与路由懒加载）。对照第五轮报告逐项核实 R5-B1~B13、R5-F1~F17、R5-T1 均已落地（不重复报告）；P1 与写路径类 P2 发现由主线逐一读盘复核确认。
> 基线状态：后端 `python manage.py test build_protection_service` 全绿（294 例，页面精简同步裁剪后）；前端 `npm run test` 全绿（30 文件 257 例）；后端 `makemigrations --check` 干净；前端 `tsc`/`vue-tsc` 通过；前端 eslint 存在 4 处格式错误（R6-F3，说明上次提交未过 lint 门禁）。
> 与前五轮的关系：第一轮约 5.5 分 → 第二轮约 7 分 → 第三轮约 7.5 分 → 第四轮约 7.5 分 → 第五轮前后端各约 8.0 分，本轮 **后端约 8.2 分、前端约 8.3 分**——页面精简的裁剪本身质量很高（迁移闭环、路由/菜单/权限/契约测试同步干净、无孤儿引用），未发现 P0 阻断问题；问题集中在三类：**①精简「只删不管」留下的运维缺口**（时段模板失去全部管理入口）；**②五轮范式在 create/update 这两个最后写入口的死角**（create 未对齐 check_conflicts 口径、update 全字段 save 丢更新）；**③「死代码 + 锁定其单测」模式第四次回潮**与注释漂移。

## 总体结论

本轮问题呈三个特征：

1. **运维面缺口首次成为 P1**：时段模板（SlotTemplate）的 CRUD 端点随「时段配置页」删除后，注释声称「写入面收敛到 seed / django-admin」，但 **SlotTemplate 从未注册进 django-admin**（精简前后均未注册）——模板只剩 seed 写死的 4 条演示数据，生产无法新增/修改/停用，时段抢占域沦为只读演示品；服务层「该时段模板已停用」分支永远不可达（R6-B1）。同族问题：django-admin 的 StrategyAdmin 删除走默认 queryset 级联，会静默抹掉 pending 借用流（R4-B1 的拦截只覆盖了 API 入口）；审计三表以完整 ModelAdmin 注册、可增删改（R6-B12）。
2. **范式推广的最后两个写入口**：`create_strategy` 恒按启用口径跑冲突校验（R5-B1 只修了 update/toggle，create 漏网——创建停用归档策略被 40902 误拦，「先停用归档再处理冲突」的官方逃生通道在 create 反而堵死，R6-B3）；`update_strategy` 仍是事务外读出实例 + 全字段 save()（R5-B5 在报告域修过的同款读改写反模式——PATCH 与 PATCH/PATCH 与 toggle 交错时丢更新、陈旧 enabled 跳过冲突校验后静默撤销他人经完整校验的重新启用，R6-B2）。另有同一资源两条写路径口径分裂：抢占 purpose 经 DRF CharField 对 int **静默强转**放行、改期路径按 R5-B9 非 str 拒绝（R6-B4）；释放原因服务层无长度守卫（R6-B5）；借用 reason 超 500 字符静默截断（R6-B7）。
3. **「死代码 + 锁定其单测」模式第四次出现**（R4-F13/R5-F17 清理过两批，本轮 R6-F4 第三批源码 + 首次出现「spec 锁定死函数」变体）：`utils/week.ts` 的 `isoWeek`/`buildMonthWeeks` 与 `utils/slotCalendar.ts` 的 `summarizeCalendar` 生产零引用，却仍有 39 行单测在守护它们；后端 `check_str_len`/`require_admin` 生产零调用（R6-B13，check_str_len 本轮借 R6-B7 复活为真实调用点）；前端五布局从装配总线解构 24 处未使用绑定（R6-F2）；十余处注释仍指涉已删页面（R6-F11/R6-B15）。

前端另有一处功能死角：admin「单条释放他人抢占」的能力位（canReleaseOthers）算好了却没有任何 UI 入口消费，`release()` 里 R4-F2 专门修的「管理员释放他人必须填原因」prompt 分支在生产 UI 不可达（R6-F1）。

**分级：P1 = 运维面缺口 / 功能死角（可稳定复现），P2 = 并发 / 口径分裂 / 迁移就绪度，P3 = 死代码 / 注释漂移 / 细节债务。** 编号规则：R6-Bx 后端、R6-Fx 前端、R6-Tx 测试基建；「处置」列标明本轮修复或记录在案。对应 spec：`specs/2026-10-24-code-quality-optimization-round6-design.md`，后端回归测试集中在 `tests_quality_round6.py`。

---

## 一、后端问题清单（backend/build_protection_service，简写 bps/）

### P1（高）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R6-B1 | **时段模板失去全部管理入口，与代码自述矛盾**：页面精简删除 SlotTemplateViewSet 时注释声称写入面「收敛到 seed / django-admin」，但 SlotTemplate 从未注册进 django-admin——生产环境无法新增/修改/停用时段模板，`services/slot_booking.py` 的「该时段模板已停用」分支永远不可达，时段抢占域变成只读演示品 | `bps/views/slot_booking.py:7-8`、`bps/admin.py`（无注册） | 本轮修复：注册 SlotTemplate（可管理）+ SlotBooking/BorrowFlow 只读；同时把 StrategyAdmin 的删除路由到共享 `delete_strategy`（pending 借用流拦截在 admin 面板同样生效，补齐 R4-B1 的最后缺口） |

### P2（中）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R6-B2 | **update_strategy 全字段 save()：丢更新 + 陈旧 enabled 绕过冲突校验**（R5-B5 在报告域修过的同款反模式）：实例在视图层事务外读出，`strategy.save()` 全量写回。并发下 ① 两个 PATCH 交错，后者用陈旧快照覆盖前者已提交的改动（改时间的 PATCH 被改名的 PATCH 覆盖回去）；② PATCH 与 toggle 交错，PATCH 持陈旧 `enabled=False` → `check_conflicts=False` 跳过校验 → save 把停用态写回，**静默撤销他人经完整校验的重新启用**。SQLite IMMEDIATE 只串行化写，救不了「实例读在事务外」的陈旧快照 | `bps/services/strategies.py:182-212`（读在 `views/strategies.py:172`） | 本轮修复：事务内 select_for_update 重读实例后再做 enabled 判定与字段合并；只写实际变更字段（save(update_fields=…)，对齐 R5-B5 范式）；PATCH+PATCH / PATCH+toggle 交错回归测试 |
| R6-B3 | **create_strategy 未传 `check_conflicts=enabled`**——R5-B1 范式没推广到 create 入口：恒跑冲突校验，创建 `enabled=False` 的归档策略与既有启用策略同时段也会被 40902 误拦；DB 唯一约束只约束 enabled=True，「停用策略不占时段」语义在 create 缺位 | `bps/services/strategies.py:170` | 本轮修复：按结果态传 `check_conflicts=enabled`；补「创建停用策略不 40902」回归测试 |
| R6-B4 | **抢占 purpose 类型校验口径分裂**：DRF CharField 对 int/float **静默强转**为 str（仅拒绝 bool/dict/list），同一载荷 `{"purpose": 12345}`——POST /slot-bookings 强转 "12345" 成功入库；PATCH 改期路径按 R5-B9 非 str 拒绝 42201。R5-B9 注释「create 路径经序列化器 CharField 会拒绝非 str」对 int/float 不成立；服务层直调路径 `str()` 强转还会把 dict 存成 repr 串 | `bps/serializers/slot_booking.py:20`、`bps/services/slot_booking.py:246` | 本轮修复：服务层 create_booking 非 str 一律 42201（对齐 R5-B9 口径）；序列化器换严格 CharField（非 str 拒绝，杜绝 API 路径 int 强转）；双路径回归测试 |
| R6-B5 | **release_booking 服务层 reason 无长度守卫且 str() 强转**：`SlotBooking.release_reason` max_length=200 的上限只存在于 ReleaseBookingSerializer；服务层作为注释声明的「唯一裁决点」，直调传 300 字符或 dict（强转 repr 串）都落库，SQLite 放行、迁 PG 即 DataError → 500 | `bps/services/slot_booking.py:300` | 本轮修复：服务层补非 str 拒绝 + 长度守卫（max_len 取模型真实 200）；服务层直调回归测试 |
| R6-B6 | **BorrowFlow.borrower 为 CASCADE：删除借用人即抹掉电子流审计**：同模型 approver/target_branch 均 PROTECT，SlotBooking.user、AdminOpLog.operator、StrategyChangeLog.operator 也都 PROTECT，唯独审计链发起方 borrower 用 CASCADE——删除一个用户，其全部借用记录（含 approved 执行凭证）静默级联消失，与全库「审计记录强存活」取向相悖 | `bps/models/others.py:184-186` | 本轮修复：改 PROTECT（migration 0016）；回归测试锁定删除被拦截 |
| R6-B7 | **借用 reason 超 500 字符静默截断，「拒绝优于截断」范式越界**：`BorrowFlow.reason` 是 TextField 且是审批人要看的核心业务内容（非审计备注），`body_str(max_len=500)` 把 600 字输入静默丢 100 字——body_str 截断语义按范式仅限审计/备注类字段 | `bps/views/borrow_flow.py:172` | 本轮修复：改用 `check_str_len`（500 上限，超出 42201 拒绝）——顺带让 R6-B13 中零调用的 check_str_len 获得真实生产调用点 |

### P3（低）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R6-B8 | **panorama 待办把「自借单」计入待审批**：R5-B10 回避规则下 PM/admin 发起的借用自己永远无法审批（只能撤回），但 `pending_approval` 仍为其计数，产生不可操作的假待办 | `bps/views/panorama.py:33-39` | 本轮修复：admin/pm 分支均排除 `borrower=user`（与 `_can_approve` 完全同口径） |
| R6-B9 | **logout 无认证面每次调用写一条审计 + 跑一次清理 DELETE**：匿名/垃圾 token POST /auth/logout 一律 200 并落 username="" 的 logout 审计行，可被脚本灌噪音；现有测试固化了该行为 | `bps/views/login.py:112` | 本轮修复：仅当成功解析出用户名时写审计；更新既有断言 |
| R6-B10 | **客户端 IP 取值口径不一致（XFF 可伪造面）**：security_log 取 `REMOTE_ADDR or 整条 X-Forwarded-For`（整条直录可伪造），login 取 `REMOTE_ADDR or XFF 首段`——同一请求在登录锁定计数与审计日志可能记录不同 IP | `bps/views/__init__.py:101`、`bps/views/login.py:31-33` | 本轮修复：抽 `client_ip()` 到 views/__init__ 共用（REMOTE_ADDR 优先，XFF 取首段） |
| R6-B11 | **slot_calendar month 全角数字未按 isascii 口径硬化**：`int("２０２６")` 在 Python 合法返回 2026，绕过 parse_int/valid_hhmm 已固化的 isascii 前置范式；第五轮已记录的存量测试缺口至今未补 | `bps/services/slot_booking.py:141-144` | 本轮修复：year/mon 段 isascii+isdigit 前置校验；全角入参回归测试 |
| R6-B12 | **django-admin 审计与关联面未收敛**：SecurityLog/AdminOpLog/StrategyChangeLog 以完整 ModelAdmin 注册（可增删改审计记录）；StrategyAdmin 删除走默认级联（pending 借用流被静默抹掉，R4-B1 拦截未覆盖 admin 面板） | `bps/admin.py:56-61` | 本轮修复：审计三表改只读 ModelAdmin（禁增删改）；StrategyAdmin.delete_model/delete_queryset 路由到共享 delete_strategy |
| R6-B13 | **死助手：require_admin 生产零调用**（消费方 admin 视图已随精简删除）；check_str_len 仅剩 round4 单测在调用（本报告 R6-B7 落地后复活为真实调用点，保留） | `bps/views/__init__.py:40-44,152-162` | 本轮修复：删除 require_admin 及其引用；check_str_len 由 R6-B7 接线 |
| R6-B14 | **filters/ 空壳目录 + django_filters 双残留配置**：filters/ 源文件已删仅剩未跟踪 `__pycache__`；settings 的 INSTALLED_APPS 与 DEFAULT_FILTER_BACKENDS 仍挂 django_filters，全库已无任何 FilterSet | `bps/filters/`、`config/settings.py:40,121` | 本轮修复：删目录与两处配置 |
| R6-B15 | **注释漂移集群**（误导后来者）：services/strategies.py 模块头/create/toggle/delete 的「PM 与 admin 两入口」表述（admin 端点已删，现入口为 PM API + 借用审批 + django-admin save_model）；errors.py 40903 描述含已不存在的「启动」场景；serializers/__init__.py「每 ORM 模型一个序列化器文件」与现状不符；services/config.py「初始值由 seed/迁移保证」不实（表恒空回落 settings 默认）；views/plan.py「避免全表 annotate」与实际相反 | `bps/services/strategies.py:1,162,219,256`、`bps/errors.py:9`、`bps/serializers/__init__.py:1`、`bps/services/config.py:7`、`bps/views/plan.py:57` | 本轮修复：一次性按精简后事实改写 |
| R6-B16 | plan.py `_conflicted_ids` 对每对策略各建 2 次时间线，分支策略数增多时聚合开销平方级（当前规模无害）；注释与行为不符部分并入 R6-B15 修正 | `bps/views/plan.py:15-25` | 记录在案（规模触发再优化） |

---

## 二、前端问题清单（frontend/src）

### P1（高）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R6-F1 | **admin「单条释放他人抢占」能力位有计算、无 UI 入口**：`canRelease = reserved && mine`、`canReleaseOthers = reserved && !mine && isAdmin` 互斥；单条释放入口只有 eventActions（要求 canRelease）与详情弹窗（要求 isMine），admin 面对他人抢占 S4/S5 行内无释放按钮——`release()` 里 R4-F2 专门修的「管理员释放他人必填原因」prompt 分支生产不可达，只能进 S4 批量模式勾 1 条走两次弹框 | `views/panorama/shared/eventActions.ts:42-48`、`shared/SlotDetailDialog.vue:55-63`、`useScheduleActions.ts:245-287` | 本轮修复：eventActions 补 canReleaseOthers → 「释放」项（release() 内部已按 mine/others 分流）；eventActions.spec 补用例 |
| R6-F2 | **五个布局从 usePanoramaPage 解构 24 处未使用绑定**：装配总线刻意扁平铺开全部输出，布局层照单全收再丢弃（s1: byDay/templates/horizonDays/slotTruncated；s2: days/kpi/templates/horizonDays；s3: lastLoadedAt/days/templates/horizonDays；s4: lastLoadedAt/days/byDay/kpi/templates/horizonDays；s5: lastLoadedAt/days/events/kpi/templates/horizonDays），读者无法据解构清单判断布局真实依赖；eslint 对 .vue 块未启用 no-unused-vars 兜底 | `layouts/s1-dashboard/index.vue:222-243` 等 5 处 | 本轮修复：各布局只解构本布局消费的字段 |
| R6-F3 | **eslint 存在 4 处 prettier 格式错误，`lint:eslint`（--max-warnings 0）会红**：说明最近提交未过 lint 门禁 | `layouts/s1-dashboard/index.vue:140,276`、`views/strategy/__tests__/saveGuard.spec.ts:55,95` | 本轮修复：eslint --fix 并全量复跑 |
| R6-F4 | **「死代码 + 锁定其单测」模式第四次回潮**：`utils/week.ts` 的 `isoWeek`/`buildMonthWeeks`（唯一消费者 weekly/weekly-new 页已删）与 `utils/slotCalendar.ts` 的 `summarizeCalendar`（消费者 slot-booking 页已删）生产零引用，仅 week.spec.ts/slotCalendar.spec.ts 在测死代码 | `utils/week.ts:31-58`、`utils/slotCalendar.ts:30-48` | 本轮修复：删函数与对应 describe 块（buildMonthCells 仍被 S3 使用保留） |

### P2（中）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R6-F5 | **抢占成功后弹窗不关闭**，与其余弹窗口径不一致：BookingDialog emit("booked") 后未 emit("update:modelValue", false)；StrategyEditDialog/StrategyBorrowDialog 均成功即关 | `views/panorama/shared/BookingDialog.vue:183-205` | 本轮修复：成功后关闭（表单有 @closed resetForm，无状态残留）；补组件测试 |
| R6-F6 | **S4「批量释放」按钮无 loading/在途守卫**：串行逐条释放期间可再次点击开出第二批，与单条接口竞态放大 | `layouts/s4-board/index.vue:56-65`、`useScheduleActions.ts:371-434` | 本轮修复：总线内 batchReleasing ref + 按钮 :loading；spec 补在途断言 |
| R6-F7 | **策略配置页表单零校验，分支选项降级为空时提交非法 payload**：startNew 落 `branch_id: 0`、onSave 无字段校验、onMounted 判 templateOptions 长度但分支其实来自 branchOptions（口径错位）；/plan 失败降级空集时保存靠后端 42201 兜底 | `views/strategy/index.vue:147-157,161-199,262-264` | 本轮修复：对齐 StrategyEditDialog 三连校验（名称/时间/分支归属） |
| R6-F8 | **S2/S3 过期抢占点击只弹「仅可查看」不给详情，跨布局口径不一**：S4/S5 行内「详情」对 past slot 恒可用，S2/S3 被 past 拦截，历史抢占在两布局无法溯源 | `layouts/s2-gantt/index.vue:249-253`、`layouts/s3-month/index.vue:202-206` | 本轮修复：past slot 放行 openDetail；布局 spec 补断言 |

### P3（低）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R6-F9 | `getPanoramaTodos` 无 API 契约测试（moduleContract/contract 两个 spec 均未覆盖 /panorama/todos 的 URL 拼装） | `api/panorama.ts:23-27` | 本轮修复：补契约用例 |
| R6-F10 | SlotDetailDialog / BookingDialog 组件零测试（均在布局 spec 中被 stub），释放确认/:loading/改期转发/必填校验/超窗口拦截无锁定 | `views/panorama/shared/SlotDetailDialog.vue`、`BookingDialog.vue` | 本轮修复：补组件级 spec |
| R6-F11 | **注释漂移十余处仍指涉已删页面**：useScheduleData「原 useWeeklyPanorama 保留不动（回滚兜底）」（该 composable 与页面均已删）、「与 slot-booking 页同源」集群、useBranchColors「供周视图与日视图共用」、borrowFormat「审批页一键复制」、StrategyBorrowDialog「weekly-new 侧不监听」、s3「复用 slot-booking 既有月历组件」、helpers「与 useWeeklyPanorama.spec 风格一致」（该文件不存在）等 | 多处 | 本轮修复：一次性改写为「与后端 XX 校验一致」式表述 |
| R6-F12 | appUrl.spec 用例样例引用已删页面路径（/report/detail/5、borrow-flow/index）——纯函数测试有效，仅样例脱节 | `utils/__tests__/appUrl.spec.ts:8,14` | 本轮修复：换现役路由样例 |
| R6-F13 | `monthsOf` 截断链路在五布局现有范围能力下恒不可达（休眠防御逻辑，有测试锁定，不算错误）——需注释标注触发条件，避免下一轮误判为死代码 | `useScheduleData.ts:57-69` | 本轮修复：注释标注「预留自定义范围场景」 |
| R6-F14 | 基座残留死文件（不影响构建）：plugins/echarts.ts（main.ts import 已注释）、components/RePureTableBar/、components/ReCol/、utils/print.ts、utils/preventDefault.ts、utils/propTypes.ts、api/user.ts 的 getLogin 死导出 | 各处 | 本轮修复：逐一 grep 复核零引用后删除（有引用则保留并记录） |
| R6-F15 | sources/strategySource.ts 直接 `as Role` cast（靠 canEditPanorama 白名单兜底，安全但未收窄）；strategy 页 onMounted 串行 await（load→loadMeta 内两请求亦串行，三请求可并行省一档首屏 RTT） | `sources/strategySource.ts:54`、`views/strategy/index.vue:253-255` | 本轮修复：入口 isRole 收窄；loadMeta 内两请求 Promise.allSettled 并行（onMounted 保持 load→loadMeta 串行以保模板降级提取正确性） |
| R6-F16 | **「挂载即开」弹窗的初始化钩子永不触发（R6-F10 新增测试实证，实施期发现）**：ScheduleDialogs 以 `v-if` 挂载三个弹窗（挂载即 modelValue=true），而 StrategyEditDialog/BookingDialog 的初始化挂在 `watch(() => props.modelValue)`（无 immediate）、StrategyBorrowDialog 挂在 el-dialog `@open` 事件——三种钩子在「挂载即开」下均不触发：编辑弹窗表单不回填、模板列表不加载（保存会以默认值 22:00 静默覆盖真实配置）；抢占弹窗 /plan 不拉取（版本/分支下拉恒空）；借用弹窗目标版本下拉恒空。weekly-new 时代弹窗为常驻挂载 + v-model 切换（watch/@open 可触发），迁入 ScheduleDialogs 改 v-if 后全部失效，R5-F14 补的 created 回触也因弹窗无法提交而不可达 | `shared/StrategyEditDialog.vue:164`、`shared/BookingDialog.vue:170`、`shared/StrategyBorrowDialog.vue:7` | 本轮修复：两处 watch 补 `immediate: true`；借用弹窗补 `onMounted(() => { if (modelValue) onOpen() })`（onOpen 幂等）；组件 spec 锁定挂载即开行为 |

---

## 三、测试基建（R6-Tx）

| 编号 | 内容 | 处置 |
|---|---|---|
| R6-T1 | 新增后端回归文件 `tests_quality_round6.py`（复用 Round4Fixture 共享夹具范式），覆盖 R6-B1~B11 全部修复点的行为锁定：admin 注册与只读面、update 并发交错、create 停用口径、purpose 双路径、释放原因服务层守卫、borrower PROTECT、reason 拒绝、todos 排除自借单、logout 审计条件、全角月份 | 本轮落地 |
| R6-T2 | 前端补测试：eventActions canReleaseOthers、BookingDialog/SlotDetailDialog 组件 spec、getPanoramaTodos 契约、S4 批量在途守卫、S2/S3 past 详情放行、strategy 页校验守卫扩展；删除锁定死函数的 describe（R6-F4 同步） | 本轮落地 |
| R6-T3 | **组件级测试两次逮住实施期回归**：① R6-F10 新建的 BookingDialog spec 暴露 getPlan 不拉取 → 顺藤查出 R6-F16 三弹窗初始化缺陷；② R6-B2 重读实例后既有 3 例断言失败（视图用陈旧实例组装响应）暴露服务层返回值未接线 → 修复视图层。结论：组件 spec 从 stub 全遮到真挂载的覆盖升级是有产出的，后续新弹窗必须带组件 spec | 本轮验证 |

### 既有测试覆盖缺口（本轮处置后仍记录在案的）

1. `PUT /api/strategies/<sid>` → 42201 方法矩阵 PUT 分支（低风险，记录在案）。
2. LayoutSwitcher `?layout=` 深链 replace + localStorage 写入（panoramaRoutes.spec 只测 resolveEntryLayout 纯函数，记录在案）。
3. MyBookingsDrawer / BorrowApprovalDrawer / EventActionMenu / ScheduleEventCard 组件级直测（逻辑经总线与布局 spec 间接覆盖，记录在案）。
4. 基座 `utils/http` 401 刷新链路（pure-admin 基座，按口径不要求）。

---

## 四、死代码 / 残留清单（页面精简专项，逐项 grep 核实）

| 对象 | 核实结论 |
|---|---|
| 后端 `check_str_len` / `require_admin` | 零生产调用（R6-B13：前者复活、后者删除） |
| 后端 `filters/` 目录 | 仅剩未跟踪 `__pycache__`（R6-B14 删除） |
| 后端 weekly/plan 端点 | **非死代码**：仍被调度全景页消费（api/weekly.ts、api/plan.ts），保留 |
| 后端 ExecutionRound 读路径 | 全库无写入路径（仅 django-admin 手工可写），plan 的 status 恒 pending——准死数据域，随 django-admin 保留供数，记录在案 |
| 后端 RuntimeConfig | 只读无写入口、表恒空回落 settings 默认（R6-B15 修注释，机制保留） |
| 前端 api/admin.ts、api/plan.ts、api/weekly.ts | **存活**（strategy 页 / 数据中枢 / 弹窗消费），不删 |
| 前端 api/user.ts | 部分死：getLogin 零引用删除；refreshTokenApi 经基座 401 刷新链路存活保留 |
| 前端 composables/useStrategyPreview.ts、useBranchColors.ts | 存活（注释过时部分 R6-F11 修正） |
| 前端 utils/week.ts、slotCalendar.ts | 部分死：isoWeek/buildMonthWeeks/summarizeCalendar 删除（R6-F4），其余存活 |
| 前端基座 plugins/echarts.ts、RePureTableBar、ReCol、print.ts、preventDefault.ts、propTypes.ts | 零引用（R6-F14 逐一复核后删除） |
| 已删页面的路由/菜单/权限残留 | **无**：asyncRoutes 仅 strategy + panoramaRoute，welcome 入口已同步 2 个 |

---

## 五、做得好的方面

- **页面精简的收尾质量高**：手写迁移 0015 显式 RemoveConstraint 先于 RemoveField 规避 SQLite 重建表坑且 `makemigrations --check` 干净；前端路由/欢迎页/API 契约测试/常量注释同步干净，未留任何孤儿路由/菜单/权限位。
- **借用流写路径纪律扎实**：条件 UPDATE 抢占、审批失败 set_rollback 保持 pending、_flow_qs 统一防 N+1、回避规则（R5-B10）落地且有专用文案。
- **IntegrityError 双格式匹配**（SQLite 字段名式 + PG 约束名式）在 strategies 与 slot_booking 两域均已到位并有三件套单测。
- **前端数据中枢纪律到位**：seq 双守卫（读取段 + 终写）、weekly 先行 + 四路 Promise.all、轮询退避 + document.hidden + disposed 僵尸守卫，全部有乱序/退避/卸载单测锁定。
- **HTTP 层零违反**：无 `catch (e: any)`、无深取 `e.response.data`、silent 使用精准、401 跳转统一走 appHashUrl；权限位与展示映射唯一来源成立（28 个权限口径用例）。
- **安全默认姿态好**：生产缺 SECRET_KEY 拒绝启动、DEBUG/CORS 默认收紧、登录限流 add+incr 原子固定窗口。

**总体判断**：按既有分级折算，本轮后端约 8.2 分、前端约 8.3 分——五轮治理 + 页面精简后主链路扎实，剩余问题集中在「精简只删不管的运维面」与「最后两个写入口」。修复 R6-B1~B7 与 R6-F1~F8 后可回到 8.6 一线。
