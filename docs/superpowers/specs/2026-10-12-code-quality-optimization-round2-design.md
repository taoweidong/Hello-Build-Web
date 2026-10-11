# 第二轮全库代码质量优化设计（2026-10-12）

输入：`docs/code-quality-assessment-2026-10-12.md`（问题编号沿用该报告）。
原则：每阶段独立可提交；**任一阶段完成后必须全量跑通该侧单元测试才进入下一阶段**；行为变化同步更新本文档与测试；模型改动出迁移文件。

> **进度（2026-10-12 回填）**：阶段一 = 820ddcc、阶段二/三 = 063d99b + a62bb9d（后端测试 198 → 279 全绿）；阶段四 = dc6fc89、阶段五主体 = e02d0d9 + 7c32038（含 weekly 载荷补 push_mode 后端项；前端 vitest/typecheck/build 全绿）。阶段五 F-P2-10/11/12 等余项与阶段六（测试补全）进行中，对应 checkbox 由实施方完成后勾选。阶段七文档同步已大部完成：AGENTS.md、README 及 slot-booking/borrow-flow/weekly-new(push_mode)/verification-report/django-migration/concurrency-guard/build-strategy-web/round1 设计各文档已按实际行为回写（2026-10-12 docs 提交）；阶段八/九待收尾。

## 阶段一：后端 P0 修复

- [x] **B-P0-1 weekdays 统一为 isoweekday 1-7（1=周一…7=周日）**：改 `serializers/slot_booking.py` 校验为 1-7 + 报错文案同步；核对前端 TemplateDialog（已是 1-7，无需改）；修 `tests_id_guard.py` 夹具（weekdays 改 1-5 口径、`_future_weekday` 用 isoweekday）；更新 `tests.py` 中按 0-6 口径断言的序列化器用例；新增回归：UI 口径"7"（周日）可建模板且 `template_applies_on` 在周日命中、"0"/"8" 被拒。
- [x] **B-P0-2 策略 name 必填校验**：`services/strategies.py` 的 `validate_strategy` 增加 name 非空/非纯空白校验（42201），create/update 两路径共用（update 仅当 body 显式携带 name 时校验）；PM 与 admin 入口自动收敛。新增测试：缺 name/空串/纯空白 → 42201（POST /strategies 与 POST /admin/strategies 各一组）。
- [x] **B-P0-3 plan 非法 date → 42201**：`views/plan.py` 对 `date` 参数做 `%Y-%m-%d` 格式校验（对齐 weekly.py 的 except ValueError 范式）。新增测试。
- [x] **B-P0-4 模板整数字段类型校验**：`views/admin.py` 模板 POST/PATCH 对 smoke_minutes/analysis_minutes 复用 `parse_int` + 非负校验 → 42201。新增测试（"abc"/-1/dict/None 显式传）。
- [x] **B-P0-5 CSRF 与 django-admin 加固**：MIDDLEWARE 补 `CsrfViewMiddleware`（DRF APIView 自带 csrf_exempt，API 不受影响，用测试验证）；app 级 `admin.py` 的 User 注册改用 Django 内置 `UserAdmin`（密码哈希组件）。新增测试：断言中间件在 settings 中；API POST 无 CSRF token 仍 200（契约不破）。

## 阶段二：后端 P1 修复

- [x] **B-P1-6 错误码全量常量化**：login/views\_\_init\_\_/weekly/executions/reports/branch_config/services.slot_booking/services.strategies 的裸数字全部替换为 `errors.py` 常量；grep 验证业务代码零魔法错误码。
- [x] **B-P1-7 toggle 方法守卫**：`views/strategies.py` toggle 仅允许 POST/PATCH（前端用 PATCH、既有测试用 POST），其余 → 42201。新增 GET 无副作用测试。
- [x] **B-P1-8 admin 三端点方法守卫**：update_version 仅 PUT/PATCH、add_branch 仅 POST、update_user 仅 PATCH；DELETE/GET → 42201 且不落库不写日志。新增测试。
- [x] **B-P1-9 执行轮次 PM 隔离**：round_detail/conclusion 对 pm 角色校验 `strategy.branch.version.pm_user == user`，否则 40301。新增测试（他版 PM 403、admin/tester 不受限）。
- [x] **B-P1-10 conclusion 原子抢占**：改为 `transaction.atomic` + `filter(id=rid, conclusion__isnull=True).update(...)`，更新行数 0 → 40902（对齐 borrow_flow 审批范式）。新增重复提交测试。
- [x] **B-P1-11 无绑定 PM fail-closed**：`views/strategies.py` pm 且无绑定版本 → 空集。新增测试。
- [x] **B-P1-12 update_strategy 值域校验**：push_mode ∈ {normal,sync}、enabled 必须为 bool、name 非空（显式携带时）；创建路径同校验 push_mode/enabled。新增测试。
- [x] **B-P1-13 生产密钥守卫**：settings 中当 `DEBUG=false` 且未设 SECRET_KEY env 且非测试进程（`"test" in sys.argv` 为 False）→ `ImproperlyConfigured` 拒绝启动。
- [x] **B-P1-14 建用户密码必填**：`POST /admin/users` 缺 password → 42201（去掉 "123456" 回退）；password 非字符串 → 42201；前端 UsersTab 创建表单同步加必填规则。新增测试。
- [x] **B-P1-15 DRF 契约异常处理器**：新增 `exception_handlers.py`，ParseError/ValidationError→42201、NotAuthenticated→40100、PermissionDenied→40301、NotFound→40401、其余→50000，响应体统一 `{code,message,data:null}`；settings 挂 `EXCEPTION_HANDLER`。新增测试：reports 端点发非法 JSON → 信封格式 42201。
- [x] **B-P1-16 登录限流联合键**：失败计数键改为 `username+IP`，他人无法远程锁死任意账号。更新/新增限流测试。

## 阶段三：后端 P2 清理与测试补齐

- [x] **B-P2-17 死代码清理**：删除 `query_int/body_int`（保留 `parse_int`，移到中立模块 `utils.py` 供 services 复用消除 `_safe_int` 重复，views 侧 re-export 兼容）；`fetch_by_id` 落地采用（替换 admin `_get_template_or_404` 等手写 fetch-or-404）；`check_build_mutex` 改用 `find_overlaps`；删除 `latest_instance`、`ExecutionRound.release_approved`（出迁移）、SlotBooking `"expired"` 死枚举（出迁移）；删除 tests.py 的 skip 用例及其直测死函数的用例同步调整。
- [x] **B-P2-18 未使用 import 清理**（6 文件）。
- [x] **B-P2-19 重复助手收敛**：`_validation_error` 收敛到 `views/__init__.py`；`_require_admin` 一行包装直接用共享 `require_admin`；`_err_resp` 并入 `fail_resp` 语义。
- [x] **B-P2-20 事务/原子性**：branch config action 包 atomic；`publish_count` 改 `F()+1`、report create/update/publish 包 atomic；borrow_flow 加"同策略同借用人 pending 唯一"partial UniqueConstraint（出迁移）+ IntegrityError→40903（`CODE_ASSOCIATION`，与 borrow-flow spec「防重复」口径一致）；last-admin 保护移入 atomic。
- [x] **B-P2-21 校验口径**：策略模板重名 → 40902；create_version 校验 pm role → 42201；is_active 严格布尔解析 → 42201；logs 未知 kind → 42201；slot admin status 值域校验 → 42201；`create_booking` 序列化器改薄（校验唯一来源留在服务层，序列化器只做类型转换）——若改动面过大则保留双写并在两处加互链注释，二选一在实现时定夺。
- [x] **B-P2-22 索引与小优化**：`ExecutionRound.exec_date` 加 db_index（出迁移）；settings 测试库注释修正；plan status_map 限定到将展示的策略 id 集；报告列表支持可选 `page/page_size`（不传保持全量，契约兼容）。
- [x] **B-P2-测试补齐**：零覆盖端点清零（admin/versions GET、admin/users POST、admin/config GET、branch-projects DELETE、executions date/from/to 过滤）+ 分支缺口（preview 冲突命中、admin toggle 撞约束、config PUT 非整数、borrow_flow 列表可见性、report publish 计数）。

## 阶段四：前端 P0/P1 修复

- [x] **F-P0-1 生产 API 地址**：`.env.production`/`.env.staging` 增加 `VITE_API_BASE_URL = /api`（同源部署相对路径，注释说明可改绝对地址）；`types/global.d.ts` ViteEnv 补声明。
- [x] **F-P0-2 initRouter 本地短路**：`router/utils.ts` 的 `initRouter` 不再请求 `/get-async-routes`，直接以本地静态路由 `handleAsyncRoutes([])`（业务路由已在 constantRoutes）；补 catch 兜底防挂起。验证 dev 登录/刷新/菜单渲染不回归。
- [x] **F-P1-3 XSS 修复**：borrow-flow 复制降级改用 `utils/clipboard.copyText`（自带转义降级）或对手动复制弹框内容做 HTML 转义。
- [x] **F-P1-4 月份切换修复**：slot-booking `setMonth` 后显式 `load()`（watcher 仅保留浏览器前进/后退场景）。
- [x] **F-P1-5 toggle 文案修正**：strategy/index.vue 与 StrategiesTab.vue 以翻转后新值出提示；`api/strategy.ts` toggleStrategy 移除误导 `enabled` 参数（后端 PATCH 无参翻转）；contract.spec 同步。
- [x] **F-P1-6 branch-config 轮询治理**：接入 `utils/polling`（退避+shouldNotify）、`document.hidden` 暂停、`api/http.ts` 增加 per-request `silent` 配置抑制轮询错误弹窗。
- [x] **F-P1-8 身份链修复**：`logOut()` 先 fire-and-forget 调 `logoutApi`（黑名单+安全日志）再本地清理；`setToken` 有效期对齐后端 JWT 实际时效；模板层刷新链死路径不再可达（配合 F-P0-2 与 mock 移除）。

## 阶段五：前端死代码清理 + P2 批量修复

- [x] **F-P1-7 死代码删除**：`views/{plan,weekly,execution,versionView,panorama,permission}`、`api/{execution,panorama}.ts`、`components/gantt/GanttGanttastic.vue`（`gantt/types.ts` 保留 STAGE_COLORS，删 GanttPhase/GanttRow）、`composables/useGanttRows.ts`、`main.ts` ganttastic 注册 + 卸载 `@infectoone/vue-ganttastic`、`mock/` 三件套 + fake-server 插件（确认无其他引用后）；`constants.ts` 删 roundConclusionMap/pushStatusMap 死符号；同步删改 polling.spec 之外的死代码测试段（composables.spec 的 useGanttRows 段）。`utils/polling.ts` 因 F-P1-6 转正保留。
- [ ] **F-P2-10/11**：6 处裸 confirm 补 try/catch；7 处加载函数补 catch（admin/index.vue 的 Promise.all 改 allSettled 或逐项 catch）。
- [ ] **F-P2-12**：strategy/index.vue 与 StrategyEditDialog 改用 `adminApi.getTemplates`，消除裸 http.get 与 as 断言。
- [ ] **F-P2-13**：api 层字面量联合类型贯彻（conclusion/status/push_mode/role 等 8 处）。
- [ ] **F-P2-14**：展示映射收敛到 constants.ts（ROLE_LABEL/ROLE_TAG、STATUS_LABEL/STATUS_TYPE、revisionTagMap、borrow statusTag、BORROW_STATUS_TEXT 迁出 api 层）。
- [ ] **F-P2-15**：hash 链接统一走 `borrowFlowUrl` 同款 origin+pathname 拼法（抽 `utils/appUrl.ts` 或并入 business.ts）。
- [ ] **F-P2-16**：BizError 兜底 code 改 -1。
- [ ] **F-P2-17/20 杂项**：detail.vue cardData 合并去重、去掉无增益转发；initNewForm 移除 DEV 假数据预填（spec 同步）；branch-config "pid=null" 文案、StrategyBorrowDialog 推送模式字段（后端 weekly payload 补 push_mode）、borrow-flow 复用 copyText、useStrategyPreview 注释与死导出 `run` 清理、strategy 预览统一 parseTime；weekly-new 首屏双请求守卫。
- [ ] **F-P2-19 品牌残留**：index.html title 与 platform-config.json Title 改"构建策略配置系统"。

## 阶段六：前端测试补全

- [ ] 新增 spec：`useStrategyOptions`、`utils/clipboard`、API 契约（admin/logs/weekly/branchConfig/slotBooking/auth/borrowFlow）、constants 补测（reportStatusMeta/roleTextMap）、`useStrategyPreview.reset`。
- [ ] 纯函数抽取后补测：slot-booking 日历 42 格装配与统计（抽 `utils/slotCalendar.ts`）、weekly-new isoWeek/monthWeeks（抽 `utils/week.ts`）、report base64Bytes/dataUrlToBlob（抽 `utils/file.ts`）。
- [ ] 更新既有 spec：composables.spec（删死段）、contract.spec（toggle 参数）、useReportForm.spec（假数据预填移除）、http.spec（BizError code -1）。

## 阶段七：文档同步

- [ ] AGENTS.md：更新测试基线数字、"AI 交互纪律"保留并强化（每次交互改动代码必须全量单测通过才允许提交）、目录结构反映死代码清理后的现状、新增约定（weekdays=isoweekday 1-7、错误码零魔法数字、展示映射唯一来源扩充）。
- [ ] 受行为变化影响的既有 specs 补记：slot-booking（weekdays 口径）、borrow-flow（pending 唯一约束、列表可见性）、weekly-new（push_mode 字段）、code-quality-optimization-design（上轮文档追加"复评见 2026-10-12 报告"链接）。
- [ ] README 如有涉及功能描述变化则同步。

## 阶段八：全量验证

- [ ] `cd backend && python manage.py test build_protection_service` 全绿（基线 198 → 目标 ≥ 240）。
- [ ] `cd frontend && npm run test` 全绿（基线 60 → 目标 ≥ 100）。
- [ ] `npm run typecheck`、`npm run build`、`npm run lint:eslint` 通过。

## 阶段九：提交

- [ ] 按阶段分多个简体中文 conventional commit（fix/refactor/test/docs/chore），全程不提交带失败的批次。

## 设计决策记录

1. **weekdays 选 isoweekday 1-7 而非序列化器的 0-6**：服务层匹配、模型 help_text、seed、既有 slot 测试、前端 UI 五处均已是 1-7，序列化器是唯一少数派；改一处 vs 改五处，且 1-7 与 Python `isoweekday()`/前端 dayjs `isoWeekday()` 天然对齐。
2. **`POST /api/branches` 权限不动**：builder 可建分支是分支配置模块被测试固化的开放协作口径（tests_branch_config.py 锁定），属业务决策非缺陷；admin 路径保留给版本管理场景。
3. **tsconfig strict 不收严**：涉及基座模板（pure-admin）数百处报错，超出本轮质量优化范围，记录为长期债务。
4. **生产 `VITE_API_BASE_URL=/api` 用相对路径**：假设前后端同源部署（nginx 反代 /api → 后端）；跨域部署时改配绝对地址即可，注释中说明。
5. **SECRET_KEY 守卫豁免测试进程**：Django 测试运行时无 .env 亦需启动，用 `"test" in sys.argv` 判别；生产（runserver DEBUG=false / gunicorn）缺密钥直接拒绝启动。
6. **mock 三件套与 fake-server 插件整体移除**：F-P0-2 短路后 asyncRoutes mock 无消费者；login/refreshToken mock 与业务登录链（api/auth.ts + 后端 JWT）无关，留着只有"误开 enableProd 可伪造管理员"的单点风险。
