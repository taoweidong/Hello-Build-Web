# AGENTS.md

构建策略配置系统：管理版本/分支的每日构建策略（构建→冒烟→人工分析→推送），提供甘特计划页、周视图、执行/变更日志、验证报告、分支配置管理。前后端分离，界面与注释均为简体中文。

## AI 交互纪律（强制）

- **每一次 AI 交互中，只要改动或新增了代码，必须先执行单元测试且全部通过，才允许提交代码**：
  - 后端：`cd backend && python manage.py test build_protection_service`（全部通过，当前基线 ≥ 150 例）。
  - 前端：`cd frontend && npm run test`（vitest，全部通过，当前基线 ≥ 32 例）；涉及类型/模板改动还需 `npm run typecheck`，涉及构建产物改动还需 `npm run build`。
  - 任一失败必须修复后重跑，禁止跳过、禁止带失败提交。
- 改某功能前先读 `docs/superpowers/specs/` 对应设计文档；行为有变化时同步更新对应文档与测试。
- 模型改动后必须 `python manage.py makemigrations build_protection_service` 并提交迁移文件（仓库惯例）。

## 目录结构

- `backend/` — Django 5 + DRF + SimpleJWT + SQLite（依赖声明在 `backend/pyproject.toml`，无 requirements.txt）。唯一业务 app：`build_protection_service/`，模型按领域拆分在 `models/`（others.py / report.py / branch_config.py / slot_booking.py）。
- `frontend/` — Vue 3 + Vite + TS + Element Plus，基于 **pure-admin-thin v6.2.0** 模板（npm，有 package-lock.json）。业务页面在 `src/views/`，业务 API 封装在 `src/api/*.ts`，跨页复用逻辑在 `src/composables/`，展示常量（结论/状态徽标映射）唯一来源在 `src/views/constants.ts`。
- `docs/superpowers/specs/` 与 `docs/superpowers/plans/` — 每个功能一份设计文档 + 一份 checkbox 实施计划。**改某功能前先读对应 spec**；新功能应同样补文档。
- `docs/code-quality-assessment-2026-10-11.md` — 代码质量评估报告（2026-10-11 全库质量优化专项的输入）。
- `prototype/` — 静态 HTML 原型；`README.md`、`业务原始背景.md` — 领域背景。

## 常用命令

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

- **根 README.md 已过时**：它描述的是最初的 FastAPI 方案；后端已于 2026-08-10 整体迁移到 Django（见 `docs/superpowers/specs/2026-08-10-django-migration-and-weekly-view-design.md`）。不要按 README 的目录/技术栈写代码。
- **统一响应契约** `{code, message, data}`：用 `api.py` 的 `ok()/err()` 组装；错误响应统一走 `views/__init__.py` 的 `fail_resp(code, message)`（HTTP 状态由 `errors.py` 的 `CODE_STATUS` 映射决定，勿手写状态码）。时间序列化统一 `"%Y-%m-%dT%H:%M:%S"`；时区 Asia/Shanghai，`USE_TZ=True`。
- **错误码常量与语义固定**（定义在 `backend/build_protection_service/errors.py`）：40100/40101 未认证（前端跳登录并清理业务用户信息）、40301 无权限、40401 不存在、42201 参数非法、**40901 = 策略时间冲突专用**（前端有专用弹框，其他场景勿复用）、40902 重名/互斥拦截、40903 重复关联/授权、40904 时段抢占冲突、42901 登录尝试过频（连续失败 5 次锁定 15 分钟）。
- **认证/登出**：JWT 认证在 `auth.py`（无效/过期/黑名单 token 均视为未认证）；`/auth/logout` 会将当前 access token 写入 `RevokedToken` 黑名单即时失效；登录失败限流用 Django cache（进程内）。
- **DRF 认证陷阱**：全局默认 `IsAuthenticated`，但每个 ViewSet 需设 `permission_classes = [AllowAny]` 并手动调 `authed_user(request)` 校验——因为 DRF 自动 401 响应不带 `code` 字段，会破坏前端契约（参考 `views/reports.py` 内注释）。
- **策略写路径统一走 `services/strategies.py`**（校验抛 `StrategyValidationError` + `transaction.atomic`），PM 入口与 admin 入口共用，禁止在视图层复制校验逻辑；运行期配置（build_minutes 等）已落库 `RuntimeConfig` 表 + 进程内缓存，重启不丢。
- **角色体系**：User 扩展 AbstractUser，`role` ∈ admin/pm/builder/tester/integrator。前端菜单权限靠 `src/router/asyncRoutes.ts` 中的 `meta.roles`（业务路由静态注册于此，由 `router/index.ts` 合并）；`mock/` 目录只是 pure-admin 基座演示，与业务无关。
- **前端两套 HTTP 层**：业务 API 一律走 `src/api/http.ts`（Axios 实例，成功解包 `data`、失败统一 reject `BizError`——catch 里直接取 `e.code`/`e.message`，勿深取 `e.response.data`）；`src/utils/http` 仅供基座（登录/动态路由 mock）使用。
- **前端展示映射唯一来源**：结论/状态/角色徽标映射用 `src/views/constants.ts`；甘特行构建用 `src/composables/useGanttRows.ts`；策略表单预览用 `useStrategyPreview.ts`；报告表单状态机用 `useReportForm.ts`。页面内禁止再复制这些逻辑。
- **前端表格开关（el-switch 启停）**：用 `:model-value` 受控 + `:loading` + 操作后重载列表，禁止 `v-model` 乐观更新后不回滚。
- **前后端直连**：`VITE_API_BASE_URL=http://localhost:8000/api`，无 vite proxy；后端默认白名单放行 `http://localhost:8848`，本地联调可在 `backend/.env` 设 `CORS_ALLOW_ALL_ORIGINS=true`。
- **种子数据**：`python manage.py seed` 创建 admin/123456 超管及演示用户（pm27a、pm27b、builder、tester，密码均 123456）；幂等守卫锚点是 Version「27A」。
- **安全默认值**：`DEBUG` 默认 false、`ALLOWED_HOSTS`/`CORS`/`JWT_SIGNING_KEY` 均可经 env 配置（模板见 `backend/.env.example`）；`backend/.env` 已 gitignore，禁止提交真实密钥。生产 mock 服务已关闭（`build/plugins.ts` enableProd=false）。
- **文案规范**：commit message 用简体中文 conventional commits（前端有 commitlint + husky 校验）；模型字段写中文 `verbose_name`；代码注释用简体中文。
- **测试风格**：后端用 Django TestCase 风格（`tests.py`、`tests_branch_config.py`、`tests_slot_booking.py`），不是 pytest；前端用 vitest（`src/**/__tests__/*.spec.ts`），测试不引入网络与真实后端。
