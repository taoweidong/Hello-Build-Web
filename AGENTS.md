# AGENTS.md

构建策略配置系统：管理版本/分支的每日构建策略（构建→冒烟→人工分析→推送），提供甘特计划页、周视图、执行/变更日志、验证报告、分支配置管理。前后端分离，界面与注释均为简体中文。

## 目录结构

- `backend/` — Django 5 + DRF + SimpleJWT + SQLite（Python ≥ 3.11，依赖声明在 `backend/pyproject.toml`，无 requirements.txt）。唯一业务 app：`build_protection_service/`，模型按领域拆分在 `models/`（others.py / report.py / branch_config.py）。
- `frontend/` — Vue 3 + Vite + TS + Element Plus，基于 **pure-admin-thin v6.2.0** 模板（npm，有 package-lock.json）。业务页面在 `src/views/`，业务 API 封装在 `src/api/*.ts`。
- `docs/superpowers/specs/` 与 `docs/superpowers/plans/` — 每个功能一份设计文档 + 一份 checkbox 实施计划。**改某功能前先读对应 spec**；新功能应同样补文档。
- `prototype/` — 静态 HTML 原型；`README.md`、`业务原始背景.md` — 领域背景。

## 常用命令

后端（在 `backend/` 下）：
```bash
python manage.py runserver                # 端口 8000，API 前缀 /api
powershell -File scripts/prestart.ps1     # 首次初始化：makemigrations + migrate + seed
powershell -File scripts/test.ps1         # 全量测试
python manage.py test build_protection_service -v 2
python manage.py test build_protection_service.tests_branch_config.SomeCase.test_x  # 单个测试
```

前端（在 `frontend/` 下）：
```bash
npm run dev        # 端口 8848（hash 路由）
npm run build      # 生产构建
npm run typecheck  # tsc + vue-tsc
npm run lint:eslint / lint:prettier / lint:stylelint
```

## 关键约定与陷阱

- **根 README.md 已过时**：它描述的是最初的 FastAPI 方案；后端已于 2026-08-10 整体迁移到 Django（见 `docs/superpowers/specs/2026-08-10-django-migration-and-weekly-view-design.md`）。不要按 README 的目录/技术栈写代码。
- **统一响应契约** `{code, message, data}`：用 `api.py` 的 `ok()/err()` 组装；视图辅助在 `views/__init__.py`（`json_resp`、`authed_user`、`parse_body`、`security_log`）。时间序列化统一 `"%Y-%m-%dT%H:%M:%S"`；时区 Asia/Shanghai，`USE_TZ=True`。
- **错误码语义固定**：40100/40101 未认证（前端跳登录）、40301 无权限、40401 不存在、42201 参数非法、**40901 = 策略时间冲突专用**（前端有专用弹框，其他场景勿复用）、40902 重名/互斥拦截、40903 重复关联/授权。
- **DRF 认证陷阱**：全局默认 `IsAuthenticated`，但每个 ViewSet 需设 `permission_classes = [AllowAny]` 并手动调 `authed_user(request)` 校验——因为 DRF 自动 401 响应不带 `code` 字段，会破坏前端契约（参考 `views/reports.py` 内注释）。
- **角色体系**：User 扩展 AbstractUser，`role` ∈ admin/pm/builder/tester/integrator。前端菜单权限靠 `src/router/asyncRoutes.ts` 中的 `meta.roles`（业务路由静态注册于此，由 `router/index.ts` 合并）；`mock/` 目录只是 pure-admin 基座演示，与业务无关。
- **前端两套 HTTP 层**：业务 API 一律走 `src/api/http.ts`（Axios 实例，自动解包 `data` 并按错误码弹窗）；`src/utils/http` 仅供基座（登录/动态路由 mock）使用。
- **前后端直连**：`VITE_API_BASE_URL=http://localhost:8000/api`，无 vite proxy，后端 `CORS_ALLOW_ALL_ORIGINS=True`。
- **种子数据**：`python manage.py seed` 创建 admin/123456 超管及演示用户（pm27a、pm27b、builder、tester，密码均 123456）；幂等守卫锚点是 Version「27A」。
- **模型改动后**必须 `python manage.py makemigrations build_protection_service` 并提交迁移文件（仓库惯例，见近期 commit）。
- 后端配置走 `backend/.env`（已 gitignore）：SECRET_KEY、DEBUG、BUILD_MINUTES、PUSH_MINUTES、ACCESS_TOKEN_EXPIRE_MINUTES 等。
- **文案规范**：commit message 用简体中文 conventional commits（前端有 commitlint + husky 校验）；模型字段写中文 `verbose_name`；代码注释用简体中文。
- 后端测试用 Django TestCase 风格（`tests.py`、`tests_branch_config.py`），不是 pytest。
