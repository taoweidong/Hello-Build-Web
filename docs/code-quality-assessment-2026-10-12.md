# 代码质量评估报告（2026-10-12，第二轮全库复评）

> 评估范围：`backend/`（Django 5 + DRF + SimpleJWT + SQLite，业务代码约 5,200 行 + 测试约 2,700 行）与 `frontend/`（Vue 3 + Vite + TS + Element Plus，pure-admin-thin v6.2.0，业务代码约 1.2 万行）。
> 评估方法：全量阅读视图/服务/模型/序列化器/API 层/视图层源码 + 全部路由与测试覆盖逐一对照 + grep 引用计数验证死代码 + 配置审查。
> 基线状态：后端 198 个测试全绿（1 skip）；前端 60 个 vitest 全绿；typecheck 通过。
> 与上一轮（2026-10-11）的关系：上轮 P0/P1 主体已修复（错误码常量模块、统一响应、策略写路径收敛、RuntimeConfig 落库、logout 黑名单、登录限流、审批事务+乐观锁、N+1、BizError 契约、composables 收敛、enableProd=false 等），本轮为**复评 + 残留死角清查**，所有结论均经读码验证，不重复报告已修复项。

## 总体结论

架构骨架已经健康：分层清晰、契约统一、并发兜底与竞态守卫成体系。本轮发现的问题集中在四类：
1. **上轮修复的"漏网路径"**——同类问题修了主路径漏了支路径（3 个可稳定复现的 500、GET 副作用端点）；
2. **约定分叉**——weekdays 三套语义互相冲突（含一个每周二必红的隐藏 flaky 测试）、错误码常量化只收敛了一半；
3. **生产就绪缺口**——前端生产构建 API 地址缺失、登录/菜单初始化依赖 dev-only mock 端点（生产必挂）、CSRF 中间件缺失、密钥硬编码回退静默启动；
4. **死代码滞留**——菜单下线后 5 个视图目录 + 配套 API/组件/依赖仍留在仓库并进入构建产物。

按严重程度分述如下。**P0 = 功能性 bug / 安全，P1 = 架构一致性 / 正确性 / 生产阻断，P2 = 细节债务。**

---

## 一、后端问题清单

### P0 — 功能性 Bug 与安全

1. **weekdays 三套约定互相冲突（真 Bug + 周期性 flaky）**：序列化器按 **0-6（0=周一）** 校验（`serializers/slot_booking.py:29-38`），服务层匹配用 **isoweekday 1-7**（`services/slot_booking.py:64-65`），模型 help_text 与 seed 与前端 TemplateDialog 均为 **1-7**。后果：UI 选"周日"（值 7）被序列化器拒绝、**无法创建周日生效的时段模板**；填 0 合法入库但永不匹配（静默失效）；填 6 以为周日实际命中周六。连带 `tests_id_guard.py:290-319` 夹具用 0-6 口径 + `weekday()` 选日，**每周二运行必红**（当前全绿只是日期巧合）。
2. **创建策略缺 name → IntegrityError → 500**：两个创建入口（`views/strategies.py:133`、`views/admin.py:448`）均 `name=body.get("name")` 无必填校验，`Strategy.name` 非空约束在 DB 层爆出，`_raise_conflict_or_reraise` 不匹配该消息 → 原样抛出 500；空串则静默入库产生无名策略。上轮"非法参数 500 修复"的漏网点。
3. **`GET /api/plan?date=abc` → strptime ValueError → 500**：`views/plan.py:31` 未校验日期格式即传入 `build_timeline` → `parse_cd`（`services/timeline.py:10-11`）抛 ValueError。同类问题 weekly/executions 均已捕获，唯独 plan 漏掉。
4. **admin 模板创建/更新：smoke_minutes/analysis_minutes 无类型校验 → 500**：`views/admin.py:264-268、300-303` 直接落库，传 `"abc"` → ValueError、负数 → CHECK 约束 IntegrityError、dict → TypeError，均未捕获。同文件 config_view 对整数有 try/except，模板路径漏掉。
5. **全局缺失 CsrfViewMiddleware，而 django-admin（会话认证）对外暴露**：`config/settings.py` MIDDLEWARE 无 CSRF 中间件 + `config/urls.py:6` 挂载 `/django-admin/`。一旦存在任何 staff 账号，其登录与全部写操作可被跨站伪造。附带：app 级 `admin.py` 用裸 `ModelAdmin` 注册 User，django-admin 内改密码会**存明文**；seed 从不设置 is_staff → 该挂载点当前纯属攻击面。

### P1 — 架构一致性与正确性

6. **错误码常量化收敛不彻底**：7 个文件约 50 处仍用魔法数字（login.py、views/\_\_init\_\_.py:134、weekly.py、executions.py、reports.py、branch_config.py、services/slot_booking.py、services/strategies.py），`errors.py` 声称唯一真源，实际一半以上调用点绕过。
7. **PM 侧 toggle 无 HTTP 方法守卫**：`views/strategies.py:161-184` 不检查 request.method，`GET /api/strategies/<sid>/toggle` 也会真实翻转落库（GET 带副作用）；admin 侧同款端点强制 PATCH，两入口语义不一致。
8. **update_version / update_user / add_branch 无方法守卫**：`views/admin.py:108-165、205-239`，GET 会执行空 body save + 写审计日志；`DELETE /api/admin/versions/<vid>` 不删任何数据却返回成功 payload——"删除成功"假象。
9. **执行轮次详情/结论无 PM 版本隔离（水平越权读取）**：`views/executions.py:60-71、74-103` 仅登录校验，PM 可枚举 rid 读取其他版本的轮次详情与执行日志；同文件列表端点却有隔离，自相矛盾。
10. **conclusion 防重检查非原子**：`views/executions.py:90-103` check-then-act 无事务，并发双提交都读到 None → 都写入；borrow_flow 审批已有"事务+条件 update 抢占"正确范式，此处未套用。
11. **未绑定版本的 PM 可见全部策略**：`views/strategies.py:75-77` `bound_version_id` 为 None 时过滤整体跳过，应 fail-closed 为空集。
12. **update_strategy 对 push_mode/enabled/name 无值域校验**：`services/strategies.py:156-160`，`PATCH {"push_mode":"xyz"}` 直接入库且行为静默漂移；enabled 收字符串 `"false"` 为真值；name 可改空串。
13. **SECRET_KEY/JWT_SIGNING_KEY 硬编码回退值随仓库公开**：`config/settings.py:11、111`，生产漏配 env 时服务**静默正常启动**，任何人可伪造 admin JWT。应生产缺失即拒绝启动。
14. **管理端建用户默认弱口令**：`views/admin.py:194-197` 不传密码即得 `123456` 账号，且 `AUTH_PASSWORD_VALIDATORS=[]` 任何弱密码都放行。
15. **DRF 无自定义 exception handler**：非法 JSON body → ParseError 走默认 handler 返回 `{"detail": ...}` 无 code 字段，破坏 `{code,message,data}` 契约；上轮统一响应只覆盖正常路径。
16. **登录限流可被武器化**：`views/login.py:37-43` 按用户名计数，攻击者可用错误密码**锁死任意用户（含 admin）15 分钟**；应改为 用户名+IP 联合键。

### P2 — 数据模型、事务与细节

17. **死代码（生产路径零引用，grep 验证）**：`views/__init__.py` 的 `query_int/body_int/fetch_by_id`（fetch_by_id 本为消除手写 fetch-or-404 而建，但各视图仍各写一套）；`services/mutex.py:find_overlaps`（check_build_mutex 内联了自己的比较逻辑）；`services/branch_config.py:latest_instance`；`ExecutionRound.release_approved` 字段全库无读写；SlotBooking `"expired"` 状态枚举从未被赋值；`tests.py:177-182` 的 skip 用例（其等待的端点早已实现且 403 已被他处覆盖）。
18. **未使用 import**：weekly/executions/logs/reports/branch_config/admin 共 6 文件约 12 处。
19. **重复助手**：`services/slot_booking._safe_int` 与 `views/__init__.parse_int` 逐字符相同；`_validation_error` 在 admin.py 与 strategies.py 各一份；`_require_admin` 一行包装 ×2；`_list_admin_strategies` 与 `list_strategies` 的过滤逻辑近乎克隆。
20. **事务/原子性缺口**：branch config action 未包 atomic（instances 路径包了，同模块双标）；`report_service.publish` 的 `publish_count += 1` 读改写无 F() 表达式（并发丢失计数）、update/create 非原子；borrow_flow pending 去重 check-then-create 无唯一约束兜底；last-admin 保护检查与 save 非原子。
21. **校验/口径杂项**：策略模板 POST 无重名检查（slot 模板有唯一约束，同类资源两种口径）；create_version 不校验 pm_user.role=="pm"（版本可挂给 builder 变无主）；update_user 的 is_active 用 `str(...).lower() in ("true","1")` 解析，垃圾值静默变**停用**；password 传 dict → set_password TypeError 500；`/admin/logs/<kind>` 未知 kind 静默落到 security 分支；slot admin 列表 status 参数不做值域校验；create_booking 服务层与序列化器**双写同一套校验**（改一处漏一处）。
22. **索引/配置债务**：`ExecutionRound.exec_date` 无 db_index 而列表支持 date/from/to 三种按日过滤；settings 注释声称"测试库为 shared-cache 内存库"与事实不符；plan 的 status_map 对全表 Strategy 做 annotate 子查询；报告列表无分页（可选 page 参数兼容式补充）；`get_config` 把 default 写进进程缓存的单机假设（已注释声明，记录在案）。

### 测试覆盖缺口（对照全部 60 条路由逐一核对）

**零覆盖端点**：`GET /admin/versions`（列表）、`POST /admin/users`（建用户）、`GET /admin/config`、`DELETE /branch-projects/<pk>`、executions 的 date/from/to 过滤（合法+非法）。
**分支缺口**：策略缺 name（P0-2）、plan 非法 date（P0-3）、模板字段非法类型（P0-4）、toggle GET 副作用（P1-7）、conclusion 的 403/422/40902/非 POST、weekdays "7"被拒与"0"永不生效（P0-1）、preview 冲突命中分支、admin toggle 撞约束 409、config PUT 非整数 422、logs 未知 kind、`_raise_conflict_or_reraise` 的 DB 约束兜底分支（名义测试实际被 mutex 提前拦截，从未走到）、report_service 非原子场景、PM 无绑定版本可见性（P1-11）。

---

## 二、前端问题清单

### P0 — 生产阻断

1. **`.env.production`/`.env.staging` 均未定义 `VITE_API_BASE_URL`**：`api/http.ts:25` `baseURL: import.meta.env.VITE_API_BASE_URL` → 生产构建 baseURL 为 undefined，全部业务 API 缺 `/api` 前缀打向前端静态源 → **全量 404**。`types/global.d.ts` 的 ViteEnv 也未声明该变量。
2. **登录与菜单初始化依赖 dev-only mock 端点 `/get-async-routes`**：`router/utils.ts:200-227` `initRouter()` 的 Promise **无 reject/catch 分支**，`getAsyncRoutes` 走无 baseURL 的模板层 http，该端点仅由 vite-plugin-fake-server 在 dev 提供（enableProd=false）→ 生产登录 `await initRouter()` **永久挂起，无法进入系统**；刷新场景侧边菜单恒为空。业务路由早已静态并入 constantRoutes，动态路由链是纯模板残留。

### P1 — 安全与功能缺陷

3. **borrow-flow 复制降级路径存储型 XSS**：`views/borrow-flow/index.vue:249-257` 剪贴板 API 失败时 `ElMessageBox.alert` 用 `dangerouslyUseHTMLString: true` 直插**未转义**的 `flow.reason/handle_comment`（他人输入）→ 构造 `<img onerror=...>` 即可在审批人（admin/pm）浏览器执行脚本。
4. **slot-booking 月份切换不重新拉取日历**：`views/slot-booking/index.vue:226-247` `setMonth` 先改 `month.value` 再 replace 路由，唯一 watcher 的条件 `value !== month.value` 恒 false → load() 永不触发，「上一月/下一月/今天」点击后 42 格全空。
5. **策略启停成功提示与实际结果相反（两处）**：`views/strategy/index.vue:189-198`、`admin/components/StrategiesTab.vue:152-161` 后端是无参翻转，前端却用**翻转前旧值**出提示——点停用提示"已启用"。`api/strategy.ts:52-56` 还发送后端忽略的 `enabled` 参数，contract.spec 把误导参数锁进了断言。
6. **branch-config 实例轮询无退避、无隐藏暂停、故障时每 5s 弹一次错误**：`views/branch-config/index.vue:262-287` 固定 setInterval + `api/http.ts:84` 对非白名单错误**无条件弹 toast**（catch 静默挡不住，弹窗发生在拦截器）；上轮产出的 `utils/polling.ts` 退避工具只被**已下线**的 execution 页引用，活页面反而没接。
7. **下线视图及配套死代码滞留并进入构建**：`views/{plan,weekly,execution,versionView,panorama}`（约 1,780 行）、`views/permission/*`、`api/{execution,panorama}.ts`、`components/gantt/GanttGanttastic.vue`、`composables/useGanttRows.ts` 均无路由引用；`router/utils.ts:27` 的 glob 为每个死视图生成 chunk，`main.ts` 全局注册的 ganttastic 死依赖进主包；`polling.spec` 与 `composables.spec` 的部分测试段在**为死代码维护测试**；`constants.ts` 的 roundConclusionMap/pushStatusMap 成为活文件里的死符号。
8. **用户身份链三处硬伤**：`store/modules/user.ts` `logOut()` 不调后端 `logoutApi`（黑名单+安全日志形同虚设）；`getMe` 从未被调用（服务端角色变更前端永不感知）；`setToken` 伪造 30 天有效期且模板层刷新链（mock `/refresh-token`）生产同样无端点、挂起请求队列永久 pending。

### P2 — 一致性与卫生

9. **类型闸未收紧**：tsconfig `strict:false`、eslint `no-explicit-any: off`（上轮未触及，本轮继续保留——收严涉及基座模板数百处报错，投入产出比低，记录为长期债务）；业务代码 `catch (e: any)`、`Record<string, any>` 若干。
10. **裸 `await ElMessageBox.confirm`**：strategy/borrow-flow×2/StrategiesTab/TemplatesTab/UsersTab 共 6 处，用户点"取消"即 Unhandled rejection；同仓库 branch-config/slot-config/report 已是正确写法。
11. **加载函数 try/finally 无 catch**：admin/index.vue 的 `Promise.all` 一损俱损、logs/report/borrow-flow/branch-config/strategy 共 7 处失败 → unhandled rejection；活页面间风格不统一。
12. **视图绕过 API 层裸调 `http.get("/admin/templates") as TemplateItem[]`**：strategy/index.vue 与 StrategyEditDialog 两处，`adminApi.getTemplates` 明明已存在。
13. **字面量联合类型未贯彻**：ReportForm.conclusion/ReportQuery.status/StrategyForm.push_mode/PlanStrategy.push_mode/UserOption.role/BookingQuery.status/admin.ts 的 role 等 8 处仍是宽 `string`；`UsersTab.vue:23` `"builder" as string` 放弃联合。
14. **constants.ts 唯一来源仍有漏网**：branch-config 的 ROLE_LABEL/ROLE_TAG、InstancesPanel 的 STATUS_LABEL/STATUS_TYPE、report/index 的 revisionTagMap、borrow-flow 的 statusTag 三元链、`api/borrowFlow.ts` 里放展示文案 BORROW_STATUS_TEXT。
15. **hash 路由形态硬编码 ×3**：`http.ts:70` 401 跳 `/#/login`、report 两页拼 `${origin}/#/...`（未含 pathname，子路径部署断链）；borrowFlow.ts 的 `borrowFlowUrl` 是正确范本。
16. **BizError 兜底 `code ?? 0`**：网络层错误得到 code=0，与信封契约"0=成功"冲突，宜用 -1。
17. **report/detail.vue 仍 1,126 行**：cardData computed 编辑/只读两分支 15 字段逐一重复；`setTimeout(resolve,100)` 魔法等待；loadHistory 无分页拉全量报告只为下拉框。`useReportForm.initNewForm` 的 DEV 假数据预填仍在（生产可摇树，开发环境"新建→直接发布"会落库假内容）。
18. **weekly-new 小问题**：首屏双请求（注释自认）；`timeRows` 对每个时间点重复调用 `tasksAtTime` 7 次；与死文件 weekly 的 isoWeek/monthWeeks 同构成对存在（删死目录即消解一半）。
19. **模板品牌/配置残留**：`index.html` title 仍是 pure-admin-thin、platform-config.json Title=PureAdmin（拼进每页 document.title）、VITE_HIDE_HOME 声明未定义、mock 三件套仍在。
20. **杂项**：slot-booking 用 pinia roles 判 admin 而其余 12 页用 localStorage 快照（双身份源）；branch-config 文案可现 "pid=null"；StrategyBorrowDialog 以 `push_start_time` 猜测推送模式（normal+固定推送时间会误标）；borrow-flow 复制未复用带降级的 `utils/clipboard.copyText`；useStrategyPreview 注释"两入口"实为三入口且导出的 `run` 无人用；strategy 预览用原生 `new Date(...)` 解析而非统一 parseTime。

### 测试覆盖缺口

现有 8 个 spec 中 `polling.spec` 与 `composables.spec` 的 useGanttRows 段在测死代码。**零覆盖的高可测模块**：`useStrategyOptions`（report 两页共用）、`utils/clipboard.copyText`（上轮修复点无测试锁定）、API 契约（admin 19 端点/logs/weekly/branchConfig/slotBooking/auth/borrowFlow 请求函数）、`constants.ts` 的 reportStatusMeta/roleTextMap、`useStrategyPreview.reset` 在途作废语义；**需抽取才可测**：slot-booking 42 格日历装配与统计（正是 P1-4 所在文件）、weekly-new isoWeek/monthWeeks、borrow-flow canApprove、report base64Bytes/dataUrlToBlob、branch-config permLabel/permTagType。

---

## 三、优先级汇总

| 级别 | 后端 | 前端 |
|---|---|---|
| P0 | weekdays 约定冲突（含周二必红 flaky）、缺 name 500、plan date 500、模板字段 500、CSRF 缺失+明文密码 admin | 生产 API 地址缺失、initRouter 生产挂起 |
| P1 | 错误码收敛、GET 副作用×4、PM 越权读取、conclusion 竞态、无绑定 PM 全可见、push_mode 校验、密钥回退、弱口令、异常处理器、限流 DoS | XSS、月份切换空白、toggle 文案反转、轮询轰炸、死代码滞留、身份链硬伤 |
| P2 | 死代码/重复助手/事务缺口/索引/校验口径 | 裸 confirm、无 catch 加载、字面量联合、constants 漏网、hash 硬编码、大文件、品牌残留 |

**保留不改（记录为设计权衡）**：`POST /api/branches` 登录即可建分支的行为已被测试固化为预期（分支配置模块的开放协作口径），本轮不动权限、仅在 spec 中记录；tsconfig strict 收严涉及基座模板海量报错，留作长期债务。

优化实施方案（分九阶段、含验收标准）见 `docs/superpowers/specs/2026-10-12-code-quality-optimization-round2-design.md`。
