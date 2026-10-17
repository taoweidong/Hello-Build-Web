# 构建策略配置系统 · Hello-Build-Web

> 面向软件构建团队的**每日构建策略**可视化配置与调度全景系统：管理版本 / 分支的「构建 → 冒烟 → 人工分析 → 推送」全流程时间编排，提供调度全景、时段借用审批、验证报告与执行/变更日志留痕。

前后端分离 · 简体中文界面 · 当前为可运行的演示实现（外部 Git / 调度系统以模拟数据接入）。

---

## ✨ 核心功能

| 模块 | 说明 |
|---|---|
| **策略周报** | 与版本策略全景同源数据的看板重塑版：KPI 指标、时间点 × 周历网格、24h 时段趋势、分支负载与热点标签可视化 |
| **版本策略全景(New)** | 「时间点 × 周一~周日」调度矩阵；对外只读查看、对内维护修改；已过期的历史任务自动置灰、仅可查看详情 |
| **借用审批** | 非本版本人员借用某时段发起电子流，由来源版本负责人审批，通过即在目标分支按新时间建策略；支持一键复制转发与借用人自行撤销 |
| **调度全景** | 态势大屏 / 时空甘特 / 月历矩阵 / 分组看板 / 时间轴流水 5 个独立页面共用一套接口与数据中枢；支持批量释放、抢占改期与跨源冲突提示 |
| **策略配置** | 版本负责人维护本版本分支的构建策略（时间 / 模板 / 推送模式），实时时间线预览与时间冲突拦截 |
| **时段抢占** | 冒烟测试时段的预约、释放、改期与月历视图 |
| **示例菜单** | 5 个占位演示页（概览卡片 / 数据表格 / 表单录入 / 时间轴 / 空态引导），不接后端，可作新页面骨架样板 |
| **验证报告** | 冒烟验证结论记录与发布留痕 |
| **分支配置 / 日志中心 / 系统管理** | 分支与工程关联配置、执行与变更日志、用户与运行参数管理 |

角色体系：`admin` / `pm` / `builder` / `tester` / `integrator`，菜单可达性与接口写权限均按角色过滤。

## 🧱 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Vue 3 · Vite · TypeScript · Element Plus（基于 pure-admin-thin v6.2.0）· Pinia · Vue Router |
| 后端 | Django 5 · Django REST Framework · SimpleJWT · django-filter · django-cors-headers |
| 数据库 | SQLite（开发 / 演示），可平滑迁移 PostgreSQL |
| 测试 | 后端 Django TestCase（≥516 例）· 前端 Vitest（≥354 例） |

统一响应契约 `{ code, message, data }`；时区 `Asia/Shanghai`；策略写路径经服务层统一校验（时间冲突 / 资源互斥）。

## 🚀 快速开始

**一键启动（Windows，仓库根目录，推荐）**
```bat
start.bat                :: 双击或命令行执行：同时启动前后端并自动打开浏览器
start.bat -Stop          :: 停止前后端服务
start.bat -Status        :: 查看服务运行状态
```
> 首次运行会自动从 `backend/.env.example` 生成 `.env` 并执行首次初始化（建库 + 种子数据）；服务以后台进程运行，日志与 PID 文件落在根目录 `logs/`。个别环境的 PowerShell 5.1 对输出重定向参数有已知缺陷，脚本会自动降级为「最小化窗口」运行，实时输出点击任务栏对应窗口查看。PowerShell 用户可等价使用 `.\start.ps1`（另支持 `-Restart` / `-NoBrowser` / `-BackendPort` / `-FrontendPort`）。

**手动分步启动**

**后端**（`backend/`）
```bash
cd backend
cp .env.example .env                      # 按需设置 JWT_SIGNING_KEY、CORS 等
powershell -File scripts/prestart.ps1     # 生成迁移 + migrate + 种子数据
python manage.py runserver                # http://localhost:8000 （API 前缀 /api）
```

**前端**（`frontend/`）
```bash
cd frontend
npm install
npm run dev                               # http://localhost:8848
```

默认演示账号 `admin` / `123456`；另有 `pm27a`、`pm27b`、`pm26b`、`builder`、`tester`、`integrator`（密码均 `123456`）。

常用命令：前端 `npm run test` / `npm run typecheck` / `npm run build`；后端 `python manage.py test build_protection_service`。

> 本地联调：前端直连 `http://localhost:8000/api`（无代理）；跨域可在 `backend/.env` 设 `CORS_ALLOW_ALL_ORIGINS=true`。

## 📁 项目结构

```
Hello-Build-Web/
├── backend/                     # Django 后端（唯一业务 app：build_protection_service）
│   ├── build_protection_service/
│   │   ├── models/              # 按领域拆分（版本/分支/策略/报告/时段/借用…）
│   │   ├── views/  services/    # 接口层 / 业务校验层
│   │   └── management/commands/ # seed 等管理命令
│   └── scripts/                 # prestart.ps1 · test.ps1
├── frontend/                    # Vue 3 前端（业务页 src/views，API 封装 src/api）
├── docs/                        # 设计与实施文档（见下）
├── prototype/                   # 早期静态 HTML 原型
└── 业务原始背景.md              # 领域与业务流程背景
```

## 📚 文档

详细设计（spec）与分阶段实施清单（plan）位于 [`docs/superpowers/`](./docs/superpowers/)，快速上手后按需深入：

| 主题 | 设计文档 |
|---|---|
| 原始需求与背景 | [原始需求分析](./docs/原始需求分析-2026-10-11.md) · [业务原始背景](./业务原始背景.md) |
| 构建策略 Web 初版 | [设计](./docs/superpowers/specs/2026-08-08-build-strategy-web-design.md) |
| Django 迁移与周视图 | [设计](./docs/superpowers/specs/2026-08-10-django-migration-and-weekly-view-design.md) |
| 版本策略全景(New) | [设计](./docs/superpowers/specs/2026-10-11-weekly-new-design.md) |
| 策略周报看板 | [设计](./docs/superpowers/specs/2026-10-12-weekly-report-page-design.md) |
| 借用电子流 | [设计](./docs/superpowers/specs/2026-10-11-borrow-flow-design.md) |
| 时段抢占 | [设计](./docs/superpowers/specs/2026-10-10-slot-booking-design.md) |
| 验证报告 | [设计](./docs/superpowers/specs/2026-08-15-verification-report-design.md) |
| 分支配置管理 | [设计](./docs/superpowers/specs/2026-08-23-branch-config-management-design.md) |
| 策略并发防护 / 日志分页 / 界面一致性 | [并发](./docs/superpowers/specs/2026-10-11-strategy-concurrency-guard-design.md) · [日志](./docs/superpowers/specs/2026-10-11-log-pagination-design.md) · [界面](./docs/superpowers/specs/2026-10-11-ui-visual-consistency-optimization.md) |

开发约定、目录规范与易踩坑点见仓库根目录 [`AGENTS.md`](./AGENTS.md)。

## 🗺️ 后续演进

- 模拟数据切换为真实数据源（Git 仓库配置读写、防护网执行结论回传驱动推送）；
- 数据库由 SQLite 升级 PostgreSQL；
- 调度变更与外部上库流程的双向同步。
