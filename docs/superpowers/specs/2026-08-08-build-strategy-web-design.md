# 构建策略配置系统（Hello-Build-Web）设计方案

> 版本：v2.0（完善版）
> 日期：2026-08-08
> 状态：已与需求方逐项确认
> 输入：`业务原始背景.md` + 交互式需求澄清

---

## 一、概述

### 1.1 业务背景

软件交付链路包含三个环节：

| 环节 | 职责 |
|---|---|
| 构建 | 负责软件仓库构建，产出的二进制用于防护网验证 |
| 防护网 | 负责测试二进制的业务功能是否正确（冒烟 + 人工分析） |
| 集成 | 负责将构建推送的代码进行集成，发布版本 |

典型流程：定时构建（30min）→ 自动吊起防护网冒烟（1H/2H/8H）→ 人工分析（0.5H/1H/2H）→ 给出结论 → 推送代码至集成仓库（20min）。

不同版本（27A/27B/26B…）有不同代码分支（master/TR5/TR6…），不同分支按不同流程场景组织每日构建策略。

### 1.2 现状痛点

1. **排期不可视**：各版本/分支的构建策略散落在口头约定或文档中，跨角色无法直观看到完整时间线；
2. **时间交错风险**：同分支多条策略缺乏冲突约束，时间交错会导致构建/防护网资源冲突；
3. **权限无隔离**：不同版本的 PM 不同，缺乏"PM 只能配置本版本策略"的系统级约束；
4. **变更不可追溯**：策略时间调整无记录，出问题无法定位"谁在何时改了什么"；
5. **结论与推送脱节**：人工分析结论靠口头/IM 传递，推送时机依赖人工盯守。

### 1.3 系统目标与本期范围

**目标**：构建一个 Web 系统，由 PM 配置不同版本、不同分支的构建策略（时间节点），串起 构建 → 冒烟 → 人工分析 → 推送 的完整流程，并提供全角色可视化看板。

**本期范围（已确认）**：
- **以前端完整流程连通为核心**，后端以 mock 方式提供全套 API（FastAPI + SQLite 种子数据，支持读写闭环）；
- 不实现真实构建/防护网/集成的驱动逻辑，推送、通知等外部依赖以 mock 适配器留痕；
- 架构上预留调度与真实对接扩展点，演进为流程编排中枢。

---

## 二、需求基线（决策记录）

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 系统边界 | 本期"配置+展示"（mock 数据），架构预留调度/外部对接扩展点 |
| 2 | 角色 | 系统管理员、PM、构建人员、防护网测试人员、集成人员（5 类） |
| 3 | 管理员职责 | 版本信息、分支信息、PM 信息、关键配置（模板/默认耗时/全局参数） |
| 4 | 结论流程 | 防护网测试人员录入结论 → 正常模式下结论通过由系统自动吊起外部推送接口（本期 mock）；构建人员仅监督推送状态 |
| 5 | 策略模型 | 一条策略 = 模板 + 构建开始时间 + 推送模式 + 启用状态；同分支多策略并存 |
| 6 | 冲突检测 | 仅同分支内，时间区间不得交错，冲突**阻止保存** |
| 7 | 变更生效 | 当日该策略尚未开始构建 → 修改当日生效；已开始 → 次日起生效 |
| 8 | 认证 | 本地账号 + JWT，认证提供者抽象为可插拔接口（预留 SSO） |
| 9 | 后端技术栈 | FastAPI + SQLAlchemy + SQLite；调度引擎预留 APScheduler |
| 10 | 通知 | 抽象消息接口，本期 mock 打印日志，后续对接真实渠道 |
| 11 | 执行监控 | 阶段级状态跟踪（待执行/进行中/成功/失败/跳过）+ 今日执行看板 |
| 12 | 日志 | 执行日志、策略变更日志、系统管理操作日志、登录安全日志（4 类） |
| 13 | PM 绑定 | PM 与版本**一对一**（一个 PM 只对应一个版本） |
| 14 | PM 可见性 | PM 可查看全局版本计划（只读），仅能配置本版本策略 |
| 15 | 前端基座 | 基于开源项目 **pure-admin-thin**（vue-pure-admin 官方精简版）开发 |
| 16 | 推送模式 | 两种：同步推送冒烟（构建前推送）、正常流程推送（结论通过后推送） |
| 17 | 同步推送约束 | 推送必须在构建开始前 20min 完成（缓冲时长管理员可调） |
| 18 | 结论作用 | 正常模式：结论控制是否推送集成与是否发布；同步模式：结论仅评估是否正式发布 |
| 19 | 新增页面 | 策略全景页：全角色只读，版本/分支筛选，策略配置 + 历史执行实践联动 |

---

## 三、系统架构

### 3.1 架构选型

**模块化单体 + 端口抽象层**（方案 A 简化版）：FastAPI 单服务内部按领域模块化，所有外部依赖抽象为端口（Port），本期挂 mock 适配器，演进时只替换适配器实现，不动领域模块。

```
┌─────────────────────────────────────────────────────────────┐
│ 前端 · Vue3 + Vite + TypeScript + Element Plus + Pinia      │
│ 基座：pure-admin-thin（布局/登录/角色路由权限内置）          │
│ 页面：登录 · 版本计划 · 今日执行 · 策略全景 · 策略配置       │
│       · 系统管理 · 日志中心                                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API（JSON · OpenAPI 契约）
┌──────────────────────────┴──────────────────────────────────┐
│ 后端 · FastAPI 单服务（模块化单体）                          │
│  领域模块：auth / version / strategy / execution /          │
│           audit / notify                                    │
│  核心服务：时间线排布 · 冲突检测 · 生效规则                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 端口抽象层（Ports & Adapters）——演进切换点                │ │
│ │  PushPort        本期 MockPush(日志留痕) → 后续真实推送   │ │
│ │  NotifyPort      本期 打印日志        → 后续 企微/邮件    │ │
│ │  AuthProviderPort 本期 本地账号       → 后续 SSO          │ │
│ │  SchedulerPort   本期 不启用          → 后续 APScheduler  │ │
│ └─────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │ SQLAlchemy ORM
┌──────────────────────────┴──────────────────────────────────┐
│ 数据层 · SQLite（种子数据初始化，支持读写闭环）               │
│ 后续可平滑升级 PostgreSQL                                    │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 关键原则

- **API 契约先行**：FastAPI 自动生成 OpenAPI 文档（/docs），前端按契约开发；
- **mock 不 mock 契约**：所有 API 的请求/响应结构与真实版一致，后续切换零前端改动；
- **读写闭环**：策略编辑、结论录入等写操作真实落库，保证前端流程完整连通；
- **演进路径**：替换适配器实现 → 启用调度 → 必要时拆分独立 Worker，均不改动领域模块。

---

## 四、角色与权限模型

### 4.1 角色定义

| 角色 | 核心职责 | 系统中的关键操作 |
|---|---|---|
| 系统管理员 | 系统基础数据维护 | 版本/分支管理、用户管理与角色分配、PM 绑定、策略模板与关键配置 |
| PM（项目经理） | 制定本版本构建策略 | 配置/修改**本版本**分支的策略（构建开始时间、推送模式、启停）；查看全局计划（只读） |
| 构建人员 | 保障构建与推送功能 | 查看构建计划、监督推送状态（推送由系统自动触发） |
| 防护网测试人员 | 冒烟验证与人工分析 | 查看冒烟排期、**录入人工分析结论**（通过/不通过+备注） |
| 集成人员 | 接收推送、发布版本 | 查看推送/集成状态 |

### 4.2 页面 × 角色权限矩阵

| 页面 / 能力 | 管理员 | PM | 构建 | 防护网 | 集成 |
|---|---|---|---|---|---|
| 版本计划甘特看板 | ✅ 全部 | ✅ 全部(只读) | ✅ | ✅ | ✅ |
| 今日执行看板 | ✅ 查看 | ✅ 本版本 | ✅ 推送状态 | ✅ **录入结论** | ✅ 集成状态 |
| 策略全景（只读） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 策略配置 | — | ✅ **仅本版本分支** | — | — | — |
| 系统管理 | ✅ 唯一入口 | — | — | — | — |
| 日志中心 | ✅ 全部4类 | ✅ 本版本执行+变更 | ✅ 执行+变更 | ✅ 执行+变更 | ✅ 执行+变更 |

（「—」= 菜单不渲染且路由不可达）

### 4.3 权限实现要点

1. **页面级**：复用 pure-admin-thin 的 asyncRoutes 角色路由机制 + 路由守卫，菜单按角色动态渲染；
2. **操作级**：后端所有写接口二次校验角色；PM 的策略写接口额外校验「目标分支所属版本 = 当前用户绑定版本」，不符返回 403；
3. **版本级数据隔离**：`version.pm_user_id` 外键 **UNIQUE** 约束实现 PM↔版本双向一对一；管理员绑定 PM 时下拉仅显示未绑定版本的 pm 角色用户；
4. **数据过滤**：PM 视角的执行看板/日志接口在服务端按版本过滤。

---

## 五、核心功能：构建策略配置

### 5.1 策略模型

**一条策略 = 模板（固定阶段与耗时）+ 构建开始时间（HH:MM 每日循环）+ 推送模式 + 启用状态。**

PM 仅配置两个时间节点：
1. **构建开始时间**（如每天 22:00）；
2. **推送节点**（二选一）：构建前（同步推送冒烟）或 结论后（正常流程推送）。

冒烟、人工分析阶段由系统按模板耗时自动排布，PM 不可修改耗时。

### 5.2 两种推送模式

| 模式 | 推送时机 | 防护网结论的作用 |
|---|---|---|
| **同步推送冒烟** | 防护网结论**前**推送；推送结束 ≤ 构建开始 − 20min（缓冲），系统按「推送耗时 20min + 缓冲 20min」向前反推推送开始时间 | 仅评估本次版本是否正式发布 |
| **正常流程推送** | 冒烟 + 人工分析完成、结论录入且**通过**后，系统自动经 PushPort 触发推送 | 控制本次版本是否推送集成 + 是否发布；不通过则本轮终止 |

### 5.3 时间线排布算法

给定构建开始时间 T、模板冒烟耗时 D_s、分析耗时 D_a、全局配置（构建 30min、推送 20min、同步缓冲 20min）：

| 阶段 | 正常流程推送 | 同步推送冒烟 |
|---|---|---|
| 推送（20min） | 结论通过后触发：C_end → C_end+20min | T−40min → T−20min |
| 构建（30min） | T → T+30min | T → T+30min |
| 冒烟（D_s） | T+30min → T+30min+D_s | 同左 |
| 人工分析（D_a） | T+30min+D_s → T+30min+D_s+D_a | 同左 |
| 结论 | 分析结束后录入；通过→自动推送；不通过→终止 | 分析结束后录入；仅标记是否正式发布 |

示例（22:00 构建、8H 冒烟模板）：
- 同步模式：推送 21:20–21:40 → 构建 22:00–22:30 → 冒烟 22:30–次日06:30 → 分析 06:30–08:30 → 结论（评估发布）
- 正常模式：构建 22:00–22:30 → 冒烟 22:30–次日06:30 → 分析 06:30–08:30 → 结论通过 → 推送 08:30–08:50

**时间线允许跨天**，全程以绝对时间（日期+时刻）计算。

### 5.4 冲突检测（仅同分支内）

- **占用区间** = 推送起点（同步模式）或构建起点 → 人工分析终点；正常模式的结论后推送不占固定时段；
- 按**每日循环**在 48h 窗口内检测（防止昨日尾部与今日头部交错）；
- 保存时校验：冲突**阻止保存**，返回冲突策略名与重叠时段（错误码 40901）；
- 编辑表单实时预览冲突（红色斜纹提示，保存前调用 preview 接口）。

### 5.5 变更生效规则

- 当日该策略**尚未开始**构建 → 修改当日生效；
- 当日流程**已开始** → 本轮按旧配置继续（执行轮次快照），次日起按新时间；
- 每次保存写入策略变更日志（操作人/修改前后值/推送模式）；
- 停用策略保留配置不删除，看板不再显示。

### 5.6 模板与关键配置（管理员）

内置 3 个模板（支持增删改，被策略引用的模板不可删除）：

| 模板 | 冒烟耗时 | 分析耗时 | 典型构建时间 |
|---|---|---|---|
| 晚间全量冒烟 | 8H | 2H | 晚上（如 22:00） |
| 午间快速冒烟 | 2H | 1H | 中午（如 12:00） |
| 16_30 定点冒烟 | 1H | 0.5H | 下午 16:30 |

全局关键配置（global_config）：构建耗时 30min、推送耗时 20min、同步缓冲 20min。

---

## 六、数据库设计（SQLite + SQLAlchemy）

### 6.1 核心表

| 表 | 关键字段 | 说明 |
|---|---|---|
| `user` | id, username(唯一), password_hash, display_name, role(admin/pm/builder/tester/integrator), is_active, created_at | 用户 |
| `version` | id, name(唯一), **pm_user_id FK→user UNIQUE**, status(active/archived), created_at | 版本；pm_user_id UNIQUE 实现 PM↔版本双向一对一 |
| `branch` | id, version_id FK, name, UNIQUE(version_id,name), created_at | 分支 |
| `strategy_template` | id, name(唯一), smoke_minutes, analysis_minutes, description, created_by FK, updated_at | 策略模板（name 唯一约束与 smoke/analysis_minutes 非负整数校验于 2026-10-12 补齐，重名 → 40902） |
| `strategy` | id, branch_id FK, template_id FK, name, build_start_time(HH:MM), push_mode(normal/sync), enabled, created_by FK, updated_at | 构建策略（每日循环配置） |
| `execution_round` | id, strategy_id FK, exec_date(db_index), 各阶段 start/end（绝对时间）, conclusion(pending/pass/fail), conclusion_by, conclusion_at, note, push_status, UNIQUE(strategy_id,exec_date) | 每日执行轮次实例（`release_approved` 字段已于 2026-10-12 删除，见下 §6.3） |
| `global_config` | key, value, updated_at | 全局关键配置 |

### 6.2 日志表

| 表 | 字段 | 记录时机 |
|---|---|---|
| `execution_log` | round_id, stage, event, detail, at | 各阶段状态流转、结论录入、推送触发 |
| `strategy_change_log` | strategy_id, operator, field, old_value, new_value, at | PM 每次保存策略修改 |
| `admin_op_log` | operator, action, target_type, target_id, detail, at | 管理员对版本/分支/用户/模板/配置的增删改 |
| `security_log` | username, action(login_success/login_failed/login_locked/logout/…), detail（含 `ip=… ua=…` 审计串）, created_at | 登录登出、鉴权失败（无独立 ip 列，客户端 IP/UA 由 `security_log(request=…)` 拼入 detail，2026-10-11 补齐） |

### 6.3 关键设计决策

1. **策略（配置）与执行轮次（实例）分离**：strategy 存每日循环配置；execution_round 记录每天的实际执行实例，天然支撑"变更次日生效、当日不受影响"（当日轮次按旧配置快照执行）；
2. **结论单字段**：conclusion（pending/pass/fail）控制推送；早期设计的 `release_approved`（同步模式发布标记）从未落地，已于 2026-10-12 从模型删除。结论录入改为**原子抢占**（单条 `UPDATE … WHERE conclusion IS NULL`，并发双提交后到者更新 0 行 → 40902），消除 check-then-act 竞态；
3. **种子数据**：admin 账号、27A/27B/26B 三个版本（各绑定 PM）、master/TR5/TR6 分支、5 类角色用户、3 个模板、对应策略与近 7 天模拟执行轮次；
4. **软删除**：版本/分支/策略不做物理删除，以 status/enabled 标记，保护历史日志完整性。

---

## 七、接口规范

### 7.1 通用约定

```
统一响应：{ "code": 0, "message": "ok", "data": {...} }
错误码（初版列举，2026-10 已常量化扩充，全集与语义以 backend/build_protection_service/errors.py 为准）：
        0 成功 · 40100/40101 未认证 · 40301 无权限 · 40401 不存在 ·
        40901 策略时间冲突（附冲突详情）· 40902 重名/互斥/结论重复录入 ·
        40903 重复关联/授权 · 40904 时段抢占冲突 · 42201 参数校验失败 ·
        42901 登录尝试过频
鉴权：Authorization: Bearer <JWT>
文档：后端已由 FastAPI 迁移至 Django + DRF（2026-08-10），无自动 /docs；接口以本 spec 与 views/urls.py 为准
```

权限约定：写接口服务端二次校验角色；PM 写接口额外校验版本归属；管理员接口统一前缀 `/api/admin/*`；前端 Axios 拦截器统一处理 401 跳登录 / 403 提示 / 409 冲突弹框。

### 7.2 接口清单

**认证 auth**

| 方法 | 路径 | 说明 | 角色 |
|---|---|---|---|
| POST | /api/auth/login | 登录 → JWT + 用户信息（角色/绑定版本），写安全日志 | 公开 |
| POST | /api/auth/logout | 登出，写安全日志 | 全部 |
| GET | /api/auth/me | 当前用户信息（含权限元数据） | 全部 |

**计划与策略（核心）**

| 方法 | 路径 | 说明 | 角色 |
|---|---|---|---|
| GET | /api/plan?date= | 甘特看板聚合：版本→分支→策略→各阶段时间区间+冲突标记；date 非法（非 YYYY-MM-DD）→ 42201；status 经关联子查询取当日轮次结论 | 全部 |
| GET | /api/strategies?version_id=&branch_id= | 策略列表（含时间线计算结果）；可见性为设计决策（2026-10-13 定案）：全员可见、PM 过滤是「默认只看绑定版本」视图语义而非安全边界；无绑定版本的 PM → 空集（fail-closed，2026-10-12）；`version_id`/`branch_id` 过滤为 `is not None` 判定，**0 值真过滤 → 空集（fail-closed，2026-10-18，与 executions 的 strategy_id 语义一致）** | 全部 |
| POST | /api/strategies/preview | 保存前预览：时间线排布+冲突检测（不落库） | PM |
| POST | /api/strategies | 新建策略（name 必填缺失 → 42201、push_mode ∈ normal/sync、enabled 布尔，校验版本归属+冲突，冲突 40901） | PM |
| PATCH | /api/strategies/{id} | 修改（开始时间/推送模式/名称），写变更日志，按生效规则应用；校验口径（2026-10-18 定案）：格式校验恒跑，**互斥/阶段冲突校验仅在结果态为启用时执行**——停用策略不占时段，改名/改时间/改推送放行，`{"enabled": false}` 可作冲突漂移策略的止血出口 | PM |
| POST/PATCH | /api/strategies/{id}/toggle | 启用/停用（无参翻转，仅 POST/PATCH，2026-10-12 加方法守卫）；走服务层 `toggle_strategy`：启用方向重跑互斥/阶段校验（40901/40902/42201）+ 条件 UPDATE 防并发（并发已翻转 → 40902，2026-10-13）；PM 侧写 StrategyChangeLog 审计 | PM |
| DELETE | /api/strategies/{id} | 删除策略；存在待审批借用流 → 40903 拦截（防级联抹掉电子流）；审计落 AdminOpLog（StrategyChangeLog 随策略级联删除，2026-10-13） | PM |

**执行 execution**

| 方法 | 路径 | 说明 | 角色 |
|---|---|---|---|
| GET | /api/executions?date=&strategy_id=&from=&to= | 执行看板/全景页：轮次阶段状态、结论、推送状态（PM 仅本版本） | 全部 |
| GET | /api/executions/rounds/{id} | 轮次详情（各阶段实际起止+执行日志）；PM 仅本版本，跨版本 → 40301（2026-10-12 补 PM 隔离） | 全部（PM 限本版本） |
| POST | /api/executions/rounds/{id}/conclusion | 录入结论（pass/fail+备注）→ 原子抢占防重（已录入 → 40902）；正常模式且通过：经 PushPort 触发推送（mock 留痕）；同步模式：仅置 push_status 空、不写发布标记（release_approved 已删除） | 防护网测试 |

**系统管理 admin（前缀 /api/admin，写操作均写管理操作日志）**

> 2026-10-12 补：写端点加请求方法守卫（update_version 仅 PUT/PATCH、add_branch 仅 POST、update_user 仅 PATCH、模板 toggle 仅 POST/PATCH），错误方法 → 42201；模板 smoke/analysis_minutes 非负整数校验（非法 → 42201），模板重名 → 40902；用户创建密码必填、is_active 严格布尔、绑定 PM 必须为 pm 角色。

> 2026-10-13 补（第三轮质量优化）：密码最小长度 6 位（创建与重置同口径）；update_user 空串密码 → 42201（显式 null 视为未提供）；改角色（离开 pm）或停用仍绑定版本 PM 的用户 → 40902（防"无主版本"，需先移交）；config PUT 改 `parse_int` + 非负校验（拒 bool/float/负数，非法 → 42201）；`security_log` detail 拼接后统一截断 255；admin logs 时间字段改走 `fmt_dt`（上海墙钟，此前 DjangoJSONEncoder 输出带 `+00:00` 的 UTC 串）。

> 2026-10-18 补（第五轮质量优化，并回填第四轮两项）：停用用户不可被指定为版本 PM（create/update_version → 42201「PM 用户已停用」，R4-B5 回填，与 R3-B6 守护同一不变量）；django-admin 面板 `StrategyAdmin.save_model` 保存前重跑服务层校验（仅启用策略，R4-B11 回填）；`/api/admin/logs/<kind>` 读端点仅 GET（非 GET → 42201，R5-B6，R3-B16 唯一漏网）；create_version 撞 PM OneToOne 约束文案统一「版本号或 PM 已占用」（R5-B8，此前误报「版本号已存在」）；update_template 变更 smoke/analysis_minutes 时响应附 `data.warnings`（引用该模板的启用策略按分支两两阶段重叠清单，仅告警不拦截，R5-B12，前端 TemplatesTab 以 ElMessage.warning 展示）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST/PATCH | /api/admin/versions · POST /{id}/branches | 版本与分支管理（含 PM 绑定，校验一对一；pm_user_id 必须为 pm 角色） |
| GET/POST/PATCH | /api/admin/users · PATCH /{id} | 用户管理（创建/启停/重置密码/角色分配；创建密码必填） |
| GET/POST/PATCH/DELETE | /api/admin/templates | 策略模板管理（被引用不可删；name 唯一，smoke/analysis_minutes 非负整数） |
| GET/PUT | /api/admin/config | 全局关键配置 |

**日志 logs**

| 方法 | 路径 | 说明 | 角色 |
|---|---|---|---|
| GET | /api/logs/execution?date=&version_id=&branch_id= | 执行日志查询 | 全部（PM 限本版本） |
| GET | /api/logs/changes?from=&to= | 策略变更日志 | 全部（PM 限本版本） |
| GET | /api/admin/logs/operations | 管理操作日志 | 管理员 |
| GET | /api/admin/logs/security | 登录安全日志 | 管理员 |

---

## 八、用户界面设计

前端基座：**pure-admin-thin**（Vue3 + Vite + TypeScript + Element Plus + Pinia），复用其布局、登录页、角色路由权限；深色主题沿用现有 prototype 视觉语言。

### 8.1 页面清单与导航

菜单（按角色动态渲染）：

| 顺序 | 页面 | 可见角色 |
|---|---|---|
| 1 | 版本计划（甘特看板，主视图） | 全部 |
| 2 | 今日执行 | 全部 |
| 3 | 策略全景（只读） | 全部 |
| 4 | 策略配置 | PM |
| 5 | 系统管理 | 管理员 |
| 6 | 日志中心 | 全部（Tab 按角色裁剪） |

管理员视角：1/2/3/5/6；PM 视角：1/2/3/4/6；执行类角色视角：1/2/3/6。

### 8.2 版本计划甘特看板（主视图）

- **跨天连续时间轴**：横轴默认"当日 18:00 → 次日 12:00"，可左右滚动/缩放；晚间构建 + 8H 冒烟的色块跨越零点不断裂；
- **纵轴分组**：版本（含 PM 名）→ 分支·策略，每策略一行；
- **色块着色**：蓝=构建、紫=冒烟、橙=人工分析、绿=推送；冲突区间红色斜纹高亮；
- **交互**：悬停色块显示详情卡片（阶段/起止时间/状态）；PM 点击本版本色块跳转策略编辑；
- **筛选**：日期选择器 + 版本/分支下拉。

### 8.3 今日执行看板

- 统计卡片：今日轮次数 / 进行中 / 待录结论 / 推送成功；
- 轮次表格：构建 / 冒烟 / 人工分析 / 结论 / 推送 五列状态流转 + 操作列；
- 「录入结论」按钮仅防护网测试角色可见 → 弹窗选择 通过/不通过 + 备注；正常模式通过后推送列自动流转（mock 留痕）；
- PM 视角仅显示本版本行；30s 轮询刷新。

### 8.4 策略全景页（全角色只读）

- 筛选栏：版本（全部/指定）→ 分支（随版本级联）→ 执行记录时间范围（默认近 7 天）；
- **① 策略配置全景区**：策略卡片网格（策略名/版本·分支/模板/构建开始时间/推送模式/启用状态），不筛选时按版本→分支分组铺开；
- **② 执行实践全景区**：点击策略卡片联动展示其历史执行轮次倒序表格（日期 × 构建/冒烟/分析/结论/推送/备注），点击行展开执行日志详情抽屉；
- 整页无编辑入口；复用策略查询与 executions 接口（不新增接口）。

### 8.5 策略配置页（PM）

表单字段：策略模板（下拉）、策略名称（默认自动生成可改）、构建开始时间（HH:MM 时间选择器，每天循环）、推送模式（正常流程推送/同步推送冒烟 二选一）、启用状态开关。

- 底部**时间线实时预览**：编辑即调用 preview 接口，展示全部阶段排布与冲突提示；
- 保存前二次确认；冲突时展示冲突详情不可保存。

### 8.6 系统管理页（管理员）

四个 Tab：
1. **版本分支**：版本列表 + PM 绑定 + 分支子表；PM 绑定下拉仅显示未绑定版本的 pm 角色用户（强制一对一）；
2. **用户管理**：创建/角色分配/启停/重置密码；
3. **策略模板**：冒烟/分析耗时配置，被引用模板删除拦截；
4. **关键配置**：构建耗时 30min / 推送耗时 20min / 同步缓冲 20min。

### 8.7 日志中心

Tab：执行日志（日期+版本+分支筛选）· 变更日志（谁/何时/把哪条策略从几点改到几点）· 管理操作（仅管理员）· 登录安全（仅管理员）。统一表格 + 时间范围筛选。

### 8.8 交互与体验要点

- 登录页复用 pure-admin 内置样式，替换品牌文案；JWT 存 localStorage，刷新自动恢复会话；
- 所有写操作二次确认弹框；成功/失败全局消息提示；409 冲突弹框展示详情；
- 执行看板 30s 轮询（本期无 WebSocket）。

---

## 九、错误处理

| 场景 | 处理方式 |
|---|---|
| 401 令牌失效/未登录 | Axios 拦截器清除令牌 → 跳登录页（记录原路径，登录后返回） |
| 403 权限不足 | 全局消息提示「无权限执行该操作」 |
| 409 策略时间冲突（40901） | 弹框展示冲突策略与重叠时段，阻止保存 |
| 409 结论重复录入（40902） | 后端幂等校验拒绝二次录入，提示查看现有结论 |
| 422 参数校验失败 | 表单内联错误提示（字段级） |
| 5xx 服务端错误 | 全局错误提示 + 后端统一异常日志 |
| 并发编辑同一策略 | 乐观锁（updated_at 比对），后提交者提示「数据已被他人修改，请刷新」 |
| Mock 推送失败模拟 | MockPush 适配器按配置概率/开关返回失败，前端展示失败态与重试入口（验证完整流转） |

---

## 十、测试策略

| 范围 | 工具 | 重点用例 |
|---|---|---|
| 后端单元测试 | pytest | 时间线排布算法（两种推送模式/跨天）、48h 冲突检测、生效规则、PM 版本归属校验 |
| 后端接口测试 | pytest + httpx | 各模块契约、错误码、角色拦截（403）、结论驱动推送流转 |
| 前端单元测试 | Vitest | 甘特时间→像素定位换算（跨天）、权限菜单过滤 |
| 前端组件测试 | Vitest + Vue Test Utils | 策略编辑表单（预览/冲突提示）、结论录入弹窗、全景页联动筛选 |
| 端到端演示 | 手动 / Playwright（可选） | 五角色完整走查：登录→配置→执行→录结论→推送→日志 |

---

## 十一、演进路线

| 阶段 | 内容 |
|---|---|
| **本期：Mock 闭环** | 前端全流程连通 · 后端 mock 数据 · 推送/通知打印留痕 |
| 阶段二：真实对接 | RealPushAdapter（对接集成仓库）· NotifyAdapter（企微/邮件）· 执行状态由外部系统回传（webhook） |
| 阶段三：编排中枢 | 启用 APScheduler 按策略自动创建轮次、驱动阶段流转 · 调度拆分独立 Worker |
| 阶段四：平台化 | SSO 接入 · SQLite→PostgreSQL · 多环境部署 · 统计报表（通过率/耗时趋势） |

---

## 十二、项目结构与技术栈

```
Hello-Build-Web/
├── frontend/                    # pure-admin-thin 基座（Vue3+Vite+TS+Element Plus+Pinia）
│   └── src/views/               # 业务页面：plan / execution / panorama / strategy / admin / logs
├── backend/                     # FastAPI
│   ├── app/api/                 # 路由层（auth/plan/strategies/executions/admin/logs）
│   ├── app/services/            # 时间线排布 / 冲突检测 / 生效规则
│   ├── app/models/              # SQLAlchemy 模型（核心 7 张 + 日志 4 张）
│   ├── app/ports/               # PushPort / NotifyPort / AuthProviderPort / SchedulerPort
│   ├── app/adapters/            # mock 实现（本期）→ real 实现（后续）
│   └── app/seed/                # 种子数据
├── prototype/                   # 现有静态原型（保留作视觉参考）
└── docs/superpowers/specs/      # 设计文档
```

| 层 | 技术 |
|---|---|
| 前端基座 | pure-admin-thin（Vue 3 + Vite + TypeScript + Element Plus + Pinia + Vue Router） |
| 后端 | Python FastAPI + SQLAlchemy + SQLite |
| 鉴权 | JWT（本地账号，AuthProviderPort 可插拔预留 SSO） |
| 调度（预留） | APScheduler |
| 测试 | pytest / httpx / Vitest / Vue Test Utils |

---

## 附录：原型参考

`prototype/index.html` 为前期静态原型（甘特看板），其视觉语言（深色主题、阶段配色：蓝构建/紫冒烟/橙分析/绿推送、红色斜纹冲突）在本系统中延续。

---

## 修订记录（2026-10-13 第三轮质量优化）

> 本 spec 为初版设计（FastAPI 方案已由 Django 迁移取代，见 `2026-08-10-django-migration-and-weekly-view-design.md`）；以下修订针对现行 Django 实现中源自本 spec 的策略/认证/日志契约。详见 `2026-10-13-code-quality-optimization-round3-design.md`。

- **toggle 启停统一走服务层（R3-B4）**：新增 `services/strategies.toggle_strategy`——启用方向重跑互斥/阶段校验，落库用条件 UPDATE `filter(id, enabled=旧值)`（rowcount=0 → 40902「已被其他操作修改」），IntegrityError → 40902 兜底保留；PM 与 admin 入口共用，消除视图层读改写竞态副本。此前 toggle 是唯一未套「条件 UPDATE 抢占」范式的写路径，且停用 A → 他分支建同刻 B → 重新启用 A 会静默绕过互斥。
- **PM 侧审计与删除保护（R3-B5）**：PM toggle 写 StrategyChangeLog（与 admin 侧 AdminOpLog 双轨口径不变）；删除策略前拦截 pending 借用流（40903），删除审计落 AdminOpLog（StrategyChangeLog.strategy 为 CASCADE 会随策略被级联抹掉）。
- **策略可见性定案（R3-B10，行为不变）**：策略计划对全员可见（与 /plan、/weekly 一致，不作安全边界）；PM 过滤为「默认只看绑定版本」视图语义；无绑定 PM fail-closed 空集维持。
- **对外时间戳统一上海墙钟（R3-B3）**：唯一实现 `views/__init__.fmt_dt`（先 `timezone.localtime` 再 strftime `"%Y-%m-%dT%H:%M:%S"` 不带 offset），executions/borrow_flow/slot_booking/branch_config/admin logs 全部收敛——此前手工 strftime 输出 UTC 墙钟（前端早 8 小时展示）、DRF 序列化器输出上海墙钟、DjangoJSONEncoder 输出带 offset UTC 串三种口径并存。
- **认证（R3-B1）**：停用/被删用户的存量 token → 40100（simplejwt `get_user` 抛 `AuthenticationFailed`，此前未捕获 → 500，前端不跳登录）；logout 清理 RevokedToken 含 `expires_at` 为 null 的行。
- **请求体守卫（R3-B2）**：`parse_body` 对合法 JSON 非对象归一 `{}`；字符串字段提取统一 `body_str`（非 str 回退 `""` 走既有必填/非法分支），登录口/分支/工程创建等非字符串载荷 500 集群消除。
- **读端点方法守卫（R3-B16）**：plan/weekly/executions/logs/me/slot_calendar/users_all 等非 GET → 42201，与写端点守卫口径一致。
- **前端**：动作类 async 处理器补全 try/catch/finally 与保存按钮 `:loading`（防 Uncaught rejection 与双击重复提交）；推送模式文案唯一来源 `views/constants.pushModeMeta`；`catch (e: any)` 全部改 `isBizError` 类型守卫。

## 修订记录（2026-10-18 第五轮质量优化）

> 详见 `2026-10-18-code-quality-optimization-round5-design.md`（R5-B1/B2/B6/B8/B11/B12/B13），回归测试集中在 `tests_quality_round5.py`；admin 域条目已并入上方「2026-10-18 补」引言（含 R4-B5/B11 回填）。

- **停用策略冲突校验仅在启用态执行（R5-B1，P1）**：`services/strategies.update_strategy` 改传 `validate_strategy(..., check_conflicts=结果态enabled)`——格式校验（name/push_mode/HH:MM）恒跑，互斥/阶段冲突校验仅结果态为启用时执行。此前对停用策略也按启用口径误拦：停用策略本不占时段（唯一约束 `uniq_active_strategy_branch_time` 只约束 enabled），却连改名都被 40902 锁死，且冲突漂移策略无法经 `PATCH {"enabled": false}` 停用止血；现与 toggle「仅启用方向重跑校验」语义对齐。PM（`views/strategies.py`）与 admin（`views/admin.py`）两入口共用服务层，一处修复两处生效。回归 `DisabledStrategyUpdateTests`。
- **唯一约束兜底双格式匹配（R5-B2）**：`_raise_conflict_or_reraise` 同时匹配 SQLite 字段名式（`strategy.branch_id` + `build_start_time`）与 PG 约束名式（`uniq_active_strategy_branch_time`），非目标约束仍 re-raise——与 `slot_booking` 版（R4-B8）对齐，迁 Postgres 后这层 DB 兜底是并发撞约束的唯一防线。回归 `StrategyConflictPrecisionTests`。
- **check_build_mutex 构建时长单源（R5-B11）**：删除函数内 `get_config("build_minutes")` 重读，目标区间与既有策略区间统一用参数 `build_min`——此前目标用调用方传参、既有策略用 config 实时值，两源不一致时互斥判定失真。回归 `MutexBuildMinSourceTests`。
- **update_template 时长变更告警（R5-B12）**：smoke/analysis_minutes 变更时对引用该模板的**启用策略**按分支分组做两两阶段重叠检测（复用 mutex 区间逻辑），响应 `data.warnings` 返回冲突策略对清单（无冲突为空数组）；**仅告警不拦截**——冲突处置走「先停用归档」逃生通道（R5-B1 口径）。create_template 不做（尚无引用）。回归 `TemplateDurationWarningTests`。
- **列表过滤 0 值 fail-closed（R5-B13）**：`filter_strategies_qs` 的 `version_id`/`branch_id` 由 truthy 判定改 `is not None`（`parse_int` 失败返回 None 即「未提供」，0 则真过滤 → 空集），与 executions 的 `strategy_id` 语义统一。回归 `FilterZeroSemanticsTests`。
- **R5-B6/B8 与第四轮 R4-B5/B11 回填**：见上方 admin 段「2026-10-18 补」引言；admin 删除策略入口收敛共享 `delete_strategy`（R4-B1）记于 borrow-flow spec 修订四。
