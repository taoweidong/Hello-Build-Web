# AGENTS.md

构建策略配置系统：管理版本/分支的每日构建策略（构建→冒烟→人工分析→推送），提供版本策略全景(New)（时间点×周一~周日矩阵）、借用审批（电子流）、策略配置、时段抢占/时段配置、验证报告、分支配置、日志中心与系统管理。前后端分离，界面与注释均为简体中文。早期甘特计划页/周视图/今日执行/策略全景/版本全景菜单已于 2026-10-11 下线并在 2026-10-12 删除对应视图代码。

## AI 交互纪律（强制）

- **每一次 AI 交互中，只要改动或新增了代码，必须先执行单元测试且全部通过，才允许提交代码**：
  - 后端：`cd backend && python manage.py test build_protection_service`（全部通过，当前基线 ≥ 279 例）。
  - 前端：`cd frontend && npm run test`（vitest，全部通过，当前基线 ≥ 104 例）；涉及类型/模板改动还需 `npm run typecheck`，涉及构建产物改动还需 `npm run build`。
  - 任一失败必须修复后重跑，禁止跳过、禁止带失败提交。
- 改某功能前先读 `docs/superpowers/specs/` 对应设计文档；行为有变化时同步更新对应文档与测试。
- 模型改动后必须 `python manage.py makemigrations build_protection_service` 并提交迁移文件（仓库惯例）。

## 目录结构

- `backend/` — Django 5 + DRF + SimpleJWT + SQLite（依赖声明在 `backend/pyproject.toml`，无 requirements.txt）。唯一业务 app：`build_protection_service/`，模型按领域拆分在 `models/`（others.py / report.py / branch_config.py / slot_booking.py）；`parsing.py` 为 views/services 两层共用的参数解析模块（`parse_int` 唯一实现，views 包 re-export）。
- `frontend/` — Vue 3 + Vite + TS + Element Plus，基于 **pure-admin-thin v6.2.0** 模板（npm，有 package-lock.json）。业务页面在 `src/views/`，业务 API 封装在 `src/api/*.ts`，跨页复用逻辑在 `src/composables/`，展示常量（结论/状态/角色/借用/实例徽标映射）唯一来源在 `src/views/constants.ts`，纯函数工具在 `src/utils/`（business / slotCalendar / week / clipboard / appUrl / polling）。
- `docs/superpowers/specs/` 与 `docs/superpowers/plans/` — 每个功能一份设计文档 + 一份 checkbox 实施计划。**改某功能前先读对应 spec**；新功能应同样补文档。
- `docs/code-quality-assessment-2026-10-11.md` — 第一轮代码质量评估报告；`docs/code-quality-assessment-2026-10-12.md` — 第二轮复评与分阶段优化方案（对应 spec：`specs/2026-10-12-code-quality-optimization-round2-design.md`）。
- `prototype/` — 静态 HTML 原型；`README.md`、`业务原始背景.md` — 领域背景。
- `start.ps1` / `start.bat` / `stop.bat` — Windows 一键启动 / 停止前后端开发服务（仓库根目录执行，日志与 PID 落 `logs/`，首次运行自动初始化 `.env` 与数据库）。

## 常用命令

一键启动（Windows，仓库根目录）：
```powershell
.\start.ps1              # 同时启动前后端（后台进程，日志/PID 落 logs/），就绪后打开浏览器
.\start.ps1 -Stop        # 停止：按 PID 进程树结束，端口占用兜底
.\start.ps1 -Status      # 查看运行状态
.\start.ps1 -Restart     # 先停后启（另支持 -NoBrowser / -BackendPort / -FrontendPort）
start.bat                # 双击等价入口；stop.bat 等价于 -Stop
```
> 首次运行自动生成 `backend/.env` 并执行 `scripts/prestart.ps1`；非首次启动会静默 `migrate` 应用已提交迁移，并用 `makemigrations --check` 检查未生成的模型迁移（有则告警，按约定需先生成并提交）。个别环境 PowerShell 5.1 的 `Start-Process -RedirectStandard*` 有已知缺陷（进程创建前抛字典关键字冲突），脚本自动降级为最小化窗口运行，不影响启动结果。

后端（在 `backend/` 下）：
```bash
python manage.py runserver                # 端口 8000，API 前缀 /api
powershell -File scripts/prestart.ps1     # 首次初始化：makemigrations + migrate + seed（需先按 backend/.env.example 创建 .env）
powershell -File scripts/test.ps1         # 全量测试
python manage.py test build_protection_service -v 2
python manage.py test build_protection_service.tests_branch_config.SomeCase.test_x  # 单个测试
```

前端（在 `frontend/` 下）：
```bash
npm run dev        # 端口 8848（hash 路由）
npm run build      # 生产构建
npm run typecheck  # tsc + vue-tsc
npm run test       # vitest 单元测试（test:watch 常驻监听）
npm run lint:eslint / lint:prettier / lint:stylelint
```

## 关键约定与陷阱

- **根 README.md 已于 2026-10-11 重写**：现为准确的项目介绍（技术栈 Django 5 + DRF + Vue3/pure-admin，功能模块、演示账号、文档索引均与代码一致）。注意 README 里给出的测试例数/演示账号是快照，若与 `python manage.py test` / `seed.py` 实际不符，以代码为准并回改 README。历史 FastAPI 方案见 `docs/superpowers/specs/2026-08-10-django-migration-and-weekly-view-design.md`。
- **统一响应契约** `{code, message, data}`：用 `api.py` 的 `ok()/err()` 组装；错误响应统一走 `views/__init__.py` 的 `fail_resp(code, message)`（HTTP 状态由 `errors.py` 的 `CODE_STATUS` 映射决定，勿手写状态码）。时间序列化统一 `"%Y-%m-%dT%H:%M:%S"`；时区 Asia/Shanghai，`USE_TZ=True`。
- **错误码常量与语义固定**（定义在 `backend/build_protection_service/errors.py`）：40100/40101 未认证（前端跳登录并清理业务用户信息）、40301 无权限、40401 不存在、42201 参数非法、**40901 = 策略时间冲突专用**（前端有专用弹框，其他场景勿复用）、40902 重名/互斥拦截、40903 重复关联/授权、40904 时段抢占冲突、42901 登录尝试过频（同一「用户名+IP」联合键连续失败 5 次锁定 15 分钟）。
- **认证/登出**：JWT 认证在 `auth.py`（无效/过期/黑名单 token 均视为未认证）；`/auth/logout` 会将当前 access token 写入 `RevokedToken` 黑名单即时失效，前端基座 `logOut()` 会调用该接口（fire-and-forget，失败不阻塞本地清理）；前端 token 有效期取 JWT 真实 `exp`（解析失败回退 8 小时）；登录失败限流用 Django cache（进程内，键为 `login:fail:<username>:<ip>`）。
- **DRF 认证陷阱**：全局默认 `IsAuthenticated`，但每个 ViewSet 需设 `permission_classes = [AllowAny]` 并手动调 `authed_user(request)` 校验（参考 `views/reports.py` 内注释）；另有 `exception_handlers.py` 的 `contract_exception_handler` 兜底，把 DRF 内置认证/权限/解析异常归一化为 `{code,message,data}` 契约（经 `REST_FRAMEWORK["EXCEPTION_HANDLER"]` 挂载），非 DRF 异常仍走 Django 默认 500 保留堆栈。
- **策略写路径统一走 `services/strategies.py`**（校验抛 `StrategyValidationError` + `transaction.atomic`；name 必填、push_mode ∈ {normal,sync}、enabled 必须布尔、build_start_time 必须 HH:MM），PM 入口与 admin 入口共用，禁止在视图层复制校验逻辑；`StrategyValidationError` → 响应统一用 `views/__init__.py` 的 `validation_error_resp`，策略列表 `version_id/branch_id` 过滤统一用 `views/strategies.filter_strategies_qs`，fetch-or-404 统一用 `views/__init__.fetch_by_id`。运行期配置（build_minutes 等）已落库 `RuntimeConfig` 表 + 进程内缓存，重启不丢。
- **写端点方法守卫**：函数视图必须显式检查 `request.method`（toggle 仅 POST/PATCH、update_version 仅 PUT/PATCH、update_user 仅 PATCH、add_branch 仅 POST 等），禁止 GET 产生副作用；PM 列表对未绑定版本的 PM 取空集（fail-closed）；执行轮次详情/结论对 PM 做版本隔离；结论提交用「条件 UPDATE 抢占」（`filter(conclusion__isnull=True).update(...)`）防并发双写，借用审批同款范式。
- **借用电子流**：列表按「与我相关」过滤（admin 全量；pm=自己发起+自己审批；其余=自己发起）；「同策略+同借用人仅一条 pending」由 DB 部分唯一约束 `uniq_pending_borrow_flow` 兜底并发，视图捕获 IntegrityError 转 40903；状态文案唯一来源在 `views/constants.ts`（`borrowStatusMeta`），复制文案 `formatBorrowFlowText` 在视图层 `views/borrow-flow/format.ts`（API 层不持有展示文案）。
- **admin 用户/模板管理硬化**：建用户密码必填（无默认弱口令）、`is_active` 严格布尔、`password/display_name` 类型守卫；版本 PM 必须为 pm 角色；策略模板名唯一（重名 40902）、整数字段非负校验；`/admin/logs/<kind>` 仅 operations/security（未知 kind 42201）；slot 记录列表 `status` 仅 reserved/released。
- **weekdays 统一口径**：时段模板适用星期全链路（序列化器校验、服务层 `isoweekday()` 匹配、模型 help_text、seed、前端 TemplateDialog）一律用 **isoweekday 1-7（1=周一…7=周日）**，空=每天；2026-10-12 已修复 0-6 与 1-7 混用（曾致周日模板无法创建），勿再引入 0 基口径。
- **角色体系**：User 扩展 AbstractUser，`role` ∈ admin/pm/builder/tester/integrator。前端菜单权限靠 `src/router/asyncRoutes.ts` 中的 `meta.roles`（业务路由静态注册于此，由 `router/index.ts` 合并）；原 `mock/` 目录（pure-admin 基座演示）已于 2026-10-12 整体删除，与业务无关。
- **前端两套 HTTP 层**：业务 API 一律走 `src/api/http.ts`（Axios 实例，成功解包 `data`、失败统一 reject `BizError`——catch 里直接取 `e.code`/`e.message`，勿深取 `e.response.data`；网络层错误（断网/超时）无业务 code，兜底 `-1`；支持请求级 `silent: true` 静默失败不弹全局 toast，轮询/登出用）；`src/utils/http` 仅供 pure-admin 基座使用。业务路由已静态注册（`asyncRoutes.ts`），`initRouter()` 本地短路，不再请求后端动态路由（dev-only mock 端点已于 2026-10-12 移除，`mock/` 三件套与 fake-server 插件已删除）。
- **前端展示映射唯一来源**：结论/状态/角色/借用/分支权限/实例状态/修订动作徽标映射用 `src/views/constants.ts`；策略表单预览用 `src/composables/useStrategyPreview.ts`；报告表单状态机用 `useReportForm.ts`（新建态不预填任何演示内容）；分支配色用 `useBranchColors.ts`；策略下拉选项用 `useStrategyOptions.ts`。页面内禁止再复制这些逻辑。（原甘特行构建 `useGanttRows.ts` 随甘特页下线已删除。）
- **前端纯函数工具层**（均已单测锁定，改视图逻辑先改工具再连线）：月历 42 格与统计 `utils/slotCalendar.ts`、ISO 周序号与本月周列表 `utils/week.ts`（isoWeek 必须用本地日历算法，UTC getter 在东八区会周中跳号）、剪贴板带降级与假成功防护 `utils/clipboard.ts`、hash 深链接 `utils/appUrl.ts`（禁止再手拼 `${origin}/#/...`）、轮询退避 `utils/polling.ts`（pollDelay 支持自定义基准/上限；活页面轮询必须接退避 + `document.hidden` 暂停 + 请求级 `silent: true`）。
- **前端表格开关（el-switch 启停）**：用 `:model-value` 受控 + `:loading` + 操作后重载列表，禁止 `v-model` 乐观更新后不回滚。
- **前后端直连**：开发环境 `VITE_API_BASE_URL=http://localhost:8000/api`，无 vite proxy；后端默认白名单放行 `http://localhost:8848`，本地联调可在 `backend/.env` 设 `CORS_ALLOW_ALL_ORIGINS=true`。生产/staging 构建（`.env.production`/`.env.staging`）设 `VITE_API_BASE_URL=/api`，同源部署经网关反代 `/api`→后端，跨域部署改为绝对地址；该变量类型声明在 `types/global.d.ts` 的 `ViteEnv`。
- **种子数据**：`python manage.py seed` 创建 admin/123456 超管及演示用户（pm27a、pm27b、pm26b、builder、tester、integrator，密码均 123456）与 27A/27B/26B 三个版本；幂等守卫锚点是 Version「27A」（以根实体为锚，而非单一人名）。
- **安全默认值**：`DEBUG` 默认 false、`ALLOWED_HOSTS`/`CORS`/`JWT_SIGNING_KEY`/`SECRET_KEY` 均可经 env 配置（模板见 `backend/.env.example`）；`backend/.env` 已 gitignore，禁止提交真实密钥。**生产（DEBUG=false）缺 `SECRET_KEY` 会 `ImproperlyConfigured` 拒绝启动**（测试进程豁免）。CSRF：全局启用 `CsrfViewMiddleware`，业务 API 统一 `csrf_exempt`（JWT 走 Authorization 头，不依赖 cookie）。生产 mock 服务已关闭（`build/plugins.ts` enableProd=false，且 fake-server 插件已移除）。
- **文案规范**：commit message 用简体中文 conventional commits（前端有 commitlint + husky 校验）；模型字段写中文 `verbose_name`；代码注释用简体中文。
- **测试风格**：后端用 Django TestCase 风格（`tests.py`、`tests_branch_config.py`、`tests_slot_booking.py`、`tests_id_guard.py`、`tests_borrow_flow.py`、`tests_strategy_concurrency.py`、`tests_quality_round2.py`——第二轮质量修复回归全在后者），不是 pytest；前端用 vitest（`src/**/__tests__/*.spec.ts`），测试不引入网络与真实后端。报告列表 API 支持可选分页（携带 `page` 参数返回 `{items,total,page,page_size}`，不携带保持全量数组，向后兼容）。
