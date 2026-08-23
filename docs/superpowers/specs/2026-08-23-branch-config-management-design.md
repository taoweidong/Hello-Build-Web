# 分支配置管理页面设计

日期：2026-08-23
状态：已确认

## 1. 背景与目标

构建策略配置系统（Vue3 + Element Plus + pure-admin-thin 前端，Django + SQLite + DRF 后端）新增「分支配置」功能模块：将代码仓库分支与工程集关联，配置每个工程的启动参数，按分支授权用户以查看者/操作者/管理员三种角色协作，并支持对关联工程进行启动/停止的实例状态模拟管理。

设计蓝本为一份 FastAPI + SQLAlchemy 的独立方案（分支/工程/权限/实例启停四块），本期按用户确认的决策适配为当前 Django 技术栈。

目标：

1. 新增独立一级菜单「分支配置」，单页管理（布局 A：左列表右详情）。
2. 复用现有 Branch 表（版本下分支），扩展仓库地址与描述字段。
3. 维护工程库（Project），分支可关联多个工程并分别启用、配置启动参数。
4. 分支级授权：VIEWER / OPERATOR / ADMIN 三种角色，系统管理员默认全权。
5. 实例状态纯模拟：启动/停止不拉起真实进程，状态按时间推进。
6. 前端 5 秒轮询当前分支的实例状态。

## 2. 关键决策（已与用户确认）

| 决策点 | 结论 |
|--------|------|
| 嵌入方式 | 按设计实现为当前 Django + Vue3 系统的新功能（FastAPI 方案仅作蓝本，不引入 FastAPI） |
| Branch 语义 | **复用现有 Branch 表**（`version` 外键必填 → 新建分支时必须选择归属版本），扩展 `repository_url`、`description` |
| 页面入口 | 独立一级菜单「分支配置」，单页（无子路由） |
| 页面布局 | 方案 A：左列表（可搜索/新建）+ 右详情（权限面板 + 三 Tab：工程关联/启动参数/运行状态） |
| 实例实现 | 纯状态机模拟：start → STARTING →（距启动 > 2s 经轮询推进）RUNNING；stop → STOPPED；不拉起进程 |
| 权限模型 | 独立分支角色 VIEWER/OPERATOR/ADMIN，与全局角色并存；系统 admin 默认等同分支 ADMIN；无授权记录用户默认只读（VIEWER） |
| 后端技术 | DRF ViewSet + Serializer（与 reports 模块一致），聚合接口手工组装嵌套结构 |
| 工程创建 | 提供 `GET/POST /api/projects/` 维护工程库；分支「添加工程」从工程库下拉选择 |
| 轮询方案 | 页面常驻 setInterval 5 秒轮询当前分支实例；切换分支/离开页面清理定时器 |
| 测试 | 后端 pytest 为主（模型约束/聚合/状态机/权限矩阵）；前端手动联调验证 + `npm run typecheck` |

## 3. 数据模型

新增领域文件 `backend/build_protection_service/models/branch_config.py`，并在 `models/__init__.py` 统一导出。

```
Branch（现有表，扩展两字段）
├── version            FK(Version)                保留现有必填语义（新建须选版本）
├── name               CharField                  与 version 保持 unique_together
├── repository_url     CharField(255, blank)      仓库地址（新增）
├── description        TextField(blank)           描述（新增）

Project（工程库，新表）
├── name               CharField(100, unique)     工程名（必填）
├── repository_url     CharField(255, blank)
├── description        TextField(blank)
├── created_at / updated_at

BranchProject（分支↔工程关联，新表）
├── branch             FK(Branch, CASCADE, related_name="branch_projects")
├── project            FK(Project, PROTECT)
├── enabled            BooleanField(default=True) 关联是否启用
├── unique_together    (branch, project)
├── created_at / updated_at

StartupConfig（启动配置，新表，每关联一份）
├── branch_project     OneToOneField(BranchProject, CASCADE, related_name="startup_config")
├── command            CharField(255)             启动命令（如 python manage.py runserver）
├── args               JSONField(default=list)    参数数组
├── env_vars           JSONField(default=dict)    环境变量字典
├── working_directory  CharField(255, blank)      工作目录（绝对路径）
├── timeout_seconds    PositiveIntegerField(default=60)  启动超时（秒）
├── auto_restart       BooleanField(default=False)       崩溃自动重启
├── raw_json           TextField(blank)           原始配置 JSON（保留）
├── updated_at

BranchPermission（分支级授权，新表）
├── branch             FK(Branch, CASCADE, related_name="permissions")
├── user               FK(User, CASCADE)
├── role               CharField(10)              VIEWER / OPERATOR / ADMIN
├── unique_together    (branch, user)             重复授权返回 40903
├── created_at

Instance（运行实例，新表，纯模拟）
├── branch_project     FK(BranchProject, CASCADE, related_name="instances")
├── status             CharField(10)              STARTING / RUNNING / STOPPED / ERROR，默认 STOPPED
├── pid                IntegerField(null)         模拟 pid（32xxx–49xxx 随机）
├── started_at         DateTimeField(null)
├── stopped_at         DateTimeField(null)
├── last_heartbeat_at  DateTimeField(null)
├── exit_code          IntegerField(null)
├── log_tail           TextField(blank)           模拟日志尾部
├── created_at / updated_at
```

## 4. API 契约

挂载 `/api`，沿用统一响应 `{code, message, data}`；错误码沿用现有体系：`40101`/`40301`/`40401`/`42201`，新增 `40903`（重复关联工程/重复授权，前端走 40901 同类弹框）。

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/branches/` | 分支列表（含版本名），按 version 排序 | 登录用户 |
| POST | `/branches/` | 创建分支（`version_id` + `name` + `repository_url` 可选）；重名返回 40901 | 登录用户 |
| DELETE | `/branches/{id}` | 删除分支（级联清理关联/配置/权限/实例） | 系统 admin 或分支 ADMIN |
| GET | `/branches/{id}/config` | 聚合配置：分支信息 + 工程关联（含启动配置）+ 各工程最新实例 + 权限成员 + 可用用户/可用工程 | 登录用户 |
| POST | `/branches/{id}/projects` | 添加工程关联（body `{ project_id, enabled }`）；重复返回 40903 | ADMIN |
| DELETE | `/branch-projects/{bp_id}` | 删除工程关联（连同启动配置/实例） | ADMIN |
| PUT | `/branch-projects/{bp_id}/config` | 更新启动参数 | ADMIN |
| POST | `/branches/{id}/permissions` | 添加/更新授权（body `{ user_id, role }`） | ADMIN |
| DELETE | `/branch-permissions/{perm_id}` | 删除授权 | ADMIN |
| GET | `/users/all` | 可用授权用户列表（启用用户，id+username+role） | 登录用户 |
| GET | `/projects/` | 工程库列表 | 登录用户 |
| POST | `/projects/` | 创建工程（body `{ name, repository_url, description }`）；重名 40901 | 登录用户 |
| GET | `/branches/{id}/instances` | 此分支全部关联工程的最新实例状态（轮询接口，内含状态推进） | 登录用户 |
| POST | `/branch-projects/{bp_id}/start` | 启动（模拟） | OPERATOR 及以上 |
| POST | `/branch-projects/{bp_id}/stop` | 停止（模拟） | OPERATOR 及以上 |

聚合配置 `GET /branches/{id}/config` 应答结构：

```json
{
  "branch": { "id": 1, "name": "master", "version_id": 27, "version_name": "27A", "repository_url": "", "description": "" },
  "branch_projects": [
    {
      "id": 1, "enabled": true,
      "project": { "id": 1, "name": "GatewayEngine", "repository_url": "", "description": "" },
      "startup_config": { "command": "", "args": [], "env_vars": {}, "working_directory": "", "timeout_seconds": 60, "auto_restart": false, "raw_json": "" },
      "latest_instance": { "id": 1, "status": "STOPPED", "pid": null, "started_at": null, "stopped_at": null, "last_heartbeat_at": null, "exit_code": null, "log_tail": "" }
    }
  ],
  "permissions": [ { "id": 1, "user_id": 3, "username": "alice", "role": "ADMIN" } ],
  "my_role": "ADMIN",
  "available_users": [ { "id": 1, "username": "alice", "role": "builder" } ],
  "available_projects": [ { "id": 1, "name": "GatewayEngine" } ]
}
```

## 5. 权限设计

| 操作 | 系统 admin | 分支 ADMIN | 分支 OPERATOR | 分支 VIEWER / 未授权（默认只读） |
|------|:---:|:---:|:---:|:---:|
| 查看聚合配置/实例/列表 | ✓ | ✓ | ✓ | ✓ |
| 启停工程 | ✓ | ✓ | ✓ | ✗（40301） |
| 管理工程关联 / 启动参数 / 授权 | ✓ | ✓ | ✗ | ✗ |
| 删除分支 | ✓ | ✓ | ✗ | ✗ |

- 系统 admin（`role == "admin"`）不检查分支授权记录，天然等同分支 ADMIN。
- 无授权记录的普通用户按 VIEWER 处理（只读），保证页面可用。
- 聚合响应中 `my_role` 为当前登录用户在该分支的有效角色（admin 恒为 `ADMIN`），前端据此控制按钮显隐；后端每个写接口独立校验（不依赖前端隐藏）。
- `BranchProject.enabled` 表示该工程在当前分支的启用标记（列表可见性），不影响实例启停接口的可用性。

## 6. 实例状态机（纯模拟）

```
stop ──► STOPPED ◄── stop
           ▲
           │ start
        STARTING ──(距 started_at > 2s，经 GET instances 轮询推进)──► RUNNING
           │                                                          │
           └────────────── 预留：超时无心跳/异常 → ERROR ───────────────┘
```

- `start`：不存在 RUNNING/STARTING 实例时创建新 `Instance`，置 `STARTING`，`pid` 取 32000–49999 随机，记录 `started_at`、`last_heartbeat_at`；已存在运行中实例则返回 40903「实例已在运行」。
- 推进：`GET /branches/{id}/instances` 处理时，对每个 `STARTING` 且距 `started_at` 超过 2 秒的实例置 `RUNNING` 并刷新心跳；对每个 `RUNNING` 实例刷新 `last_heartbeat_at`（模拟心跳）。
- `stop`：仅对 `STARTING`/`RUNNING` 实例生效，置 `STOPPED`、记录 `stopped_at`、`exit_code=0`、追加 `log_tail`；已停止则静默返回当前状态。
- `ERROR`：本期仅保留枚举与字段，不做自动判定。
- 同一 `branch_project` 同时至多一个实例处于 STARTING/RUNNING。

## 7. 前端设计

### 7.1 路由与菜单

在 `frontend/src/router/asyncRoutes.ts` 新增一级菜单「分支配置」：

| 路由 | 名称 | 菜单位置 | 说明 |
|------|------|----------|------|
| `/branch-config` | BranchConfig | rank 10（日志中心之后） | 单页，无子路由 |

`meta.roles = ALL_ROLES`，所有登录用户可进入；操作能力由分支权限控制。

### 7.2 页面结构（布局 A 单页）

```
┌──────────────────────────────────────────────────────────────┐
│ 左侧：分支列表（~30%）        │ 右侧：详情区                     │
│ [搜索框][+ 新建分支]           │ 权限面板：成员 tag + 添加/删除授权 │
│ ─────────────────            │ Tab: ①工程关联 ②启动参数 ③运行状态 │
│ 27A / master ← 选中           │ ① 工程表格（名称/仓库/启用/操作）  │
│ 27A / TR5                    │    + 添加工程（下拉选工程库）      │
│ 26B / TR6                    │ ② 启动参数表单（ADMIN 可编辑）     │
└──────────────────────────────┴────────────────────────────────┘
```

- **左列表**：分支条目显示 `{版本} / {分支名}`；搜索框按名称/版本过滤；「+ 新建分支」弹窗：版本下拉（复用现有版本列表）、名称、仓库地址（可选）。
- **权限面板**（详情区顶部）：当前分支授权成员 tag（颜色区分角色：查看者灰/操作者蓝/管理员紫）+「＋添加授权」下拉选用户与角色；member 行带删除。仅 ADMIN 可见编辑入口。
- **Tab① 工程关联**：表格（工程名、仓库地址、启用 `el-switch`、操作：编辑参数/启动/停止/移除）；「添加工程」从 `available_projects` 下拉多选。
- **Tab② 启动参数**：表单（command、args 动态数组、env_vars 动态键值、working_directory、timeout_seconds、auto_restart、raw_json 只读展示）；ADMIN 可编辑保存，其余只读。
- **Tab③ 运行状态**：表格（工程名、状态 tag、pid、启动时间、停止时间、最近心跳、退出码、日志尾部）；启停按钮 OPERATOR 及以上可见。
- 状态 tag 颜色：STARTING 蓝 / RUNNING 绿 / STOPPED 灰 / ERROR 红。

### 7.3 数据流与轮询

1. 进入页面 → `GET /branches/` 加载列表，默认选中首项（无数据则显示空态引导新建）。
2. 选中分支 → `GET /branches/{id}/config` 拉取聚合数据 → 渲染权限面板与三个 Tab。
3. 页面常驻 `setInterval`(5s) → `GET /branches/{id}/instances` 仅刷新当前分支实例；**切换分支、组件卸载时 `clearInterval`**。
4. 每次写操作（添加工程/更新参数/启停/授权）成功后刷新聚合配置与实例。

### 7.4 API 封装与类型

- 新增 `frontend/src/api/branchConfig.ts`：封装全部接口，TypeScript 类型（Branch/Project/BranchProjectItem/StartupConfig/Instance/BranchPermission/BranchConfigResponse）内聚于此文件。
- 复用 `src/api/http.ts` 统一拦截（40101 跳登录 / 40301 提示 / 40901 冲突弹框 / 40903 重复提示 / 42201 校验信息）。
- 新建分支、添加工程、授权、启停等操作按钮均带 loading 防连点；删除类操作 `ElMessageBox` 确认。

## 8. 错误处理

- `40101` 未认证 → 拦截器跳登录
- `40301` 非管理员改工程/参数/授权、非 OPERATOR 启停 → 拦截器提示「无权限执行该操作」
- `40401` 分支/关联/实例不存在 → 提示并刷新列表
- `40901` 分支/工程重名 → 冲突弹框
- `40903` 重复授权、重复关联工程、重复启动 → 提示「记录已存在/实例已在运行」
- `42201` 必填缺失、role 非法 → 提示后端 message

## 9. 测试计划

**后端**（`build_protection_service/tests.py`，沿用现有 pytest 风格，fixture：admin/普通用户/版本/分支/工程）：
- 模型约束：重复 `(branch, project)`、`(branch, user)` 插入 → 40903
- 聚合接口：`GET /branches/{id}/config` 返回完整嵌套结构，关联工程含 startup_config 与 latest_instance
- 状态机：start → STARTING；轮询（模拟 >2s）→ RUNNING；stop → STOPPED 且带 stopped_at/exit_code；重复 start → 40903
- 权限矩阵：admin 全权；ADMIN 可增删关联/参数/授权；OPERATOR 可启停、改参数 40301；VIEWER 启停 40301；未授权用户仅可读
- 业务校验：空 name → 42201；分支重名 → 40901；工程关联重复 → 40903
- 分支删除：级联清理分支工程关联、启动配置、授权、实例

**前端**：
- `npm run typecheck` 通过
- 浏览器手动联调：新建分支 → 添加工程 → 编辑启动参数 → 启动/停止（观察状态流转 STARTING→RUNNING、轮询刷新）→ 授权成员 → 切换角色账号验证按钮显隐与 403 场景