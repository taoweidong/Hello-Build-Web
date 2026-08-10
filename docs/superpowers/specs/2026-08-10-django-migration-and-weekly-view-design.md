# Django 后端迁移 + 前端周视图等增强设计

日期：2026-08-10
状态：已确认

## 1. 背景与目标

本项目为构建策略配置系统（Vue3 + Element Plus + vue-ganttastic 前端，原 FastAPI + SQLModel 后端）。
本期目标：

1. 后端从 FastAPI 完全替换为 Django，新建 app `build_protection_service`，实现全部已有接口功能，使用 Django 默认用户认证+角色体系，完成前后端联调。
2. 前端需求变更：
   - 【版本计划】页面优化：点击任意事件下方显示详情，参考版本全景页，修复控制台报错。
   - 【新增】周视图页面：列显示周几，行显示指定版本指定分支的构建策略。
   - 【系统管理】新增策略配置页：管理员对 strategy 表完整 CRUD。
   - 推送时间可在任意时间节点设置，可与其他策略重叠，优化甘特图显示。
   - 互斥策略：同版本同时间节点仅一个分支可构建（资源互斥）。

## 2. 关键决策（已与用户确认）

| 决策点 | 结论 |
|--------|------|
| 后端迁移方式 | 完全替换 FastAPI，新建 Django 项目 + app `build_protection_service`，保持 API 契约不变 |
| 数据迁移 | 迁移到 Django 模型，Django migrations 建表，导入现有种子数据 |
| 角色映射 | 扩展 `AbstractUser` + 自定义 `role` 字段（admin/pm/builder/tester/integrator） |
| 推送时间建模 | 新增 `Strategy.push_start_time` 字段（HH:MM 每日循环，可空），手动配置，不参与冲突检测，可重叠 |
| 互斥策略处置 | 硬性拦截：同版本同时间点构建阶段重叠时拒绝保存（40902） |
| 周视图数据 | 展示策略配置排布（build_start_time 排序，周一至周日，按分支配色） |
| 计划页详情 | 配置详情 + 时间线 + 执行历史 |
| 周视图第二行 | 仅展示当前版本分支列表 |
| 系统策略配置 | 完整 CRUD，不受 PM 限制，冲突/互斥仍校验 |

## 3. 架构方案（已采用）

### 3.1 后端：DRF + 单 app + 统一响应封装

- Django 项目位于 `backend/`，核心 app `build_protection_service`。
- 使用 Django REST Framework（DRF）实现全部接口。
- 自定义响应封装：统一 `{code, message, data}`，错误码 `40101/40301/40901/40902/42201` 与现有契约一致。
- 认证：Django `django.contrib.auth` 的 `AbstractUser` + 自定义 `role` 字段；JWT 签发/校验保持现有登录契约 `{username,password}` → `{token,user}`。
- 前端仅需适配认证 token 获取/校验方式，其余接口路径与响应结构不变。

### 3.2 后端目录结构

```
backend/
├── manage.py
├── config/                      # Django 主配置
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py / asgi.py
├── build_protection_service/    # 核心 app（需求1）
│   ├── models.py                # 全部模型
│   ├── serializers.py           # DRF 序列化器
│   ├── views/                   # login/plan/strategies/executions/admin/logs/weekly
│   ├── services/                # conflict 冲突检测 / mutex 互斥 / timeline 时间线
│   ├── permissions.py           # 角色权限
│   ├── auth.py                  # JWT 认证适配
│   └── api.py                   # 统一响应封装
└── seed/                        # 种子数据脚本
```

## 4. 数据模型

在 `build_protection_service/models.py` 中定义，基于现有表结构用 Django ORM 重建：

| Django 模型 | 对应表 | 关键字段变更 |
|-------------|--------|-------------|
| `User` | `user` | 继承 `AbstractUser`，新增 `role`(admin/pm/builder/tester/integrator) |
| `Version` | `version` | 不变（name 唯一、pm_user_id 唯一绑定、status） |
| `Branch` | `branch` | 不变（version_id + name 唯一约束） |
| `StrategyTemplate` | `strategy_template` | 不变 |
| `Strategy` | `strategy` | **新增 `push_start_time`**（HH:MM，可空） |
| `ExecutionRound` | `execution_round` | 不变 |
| `ExecutionLog` | `execution_log` | 不变 |
| `StrategyChangeLog` | `strategy_change_log` | 不变 |
| `AdminOpLog` | `admin_op_log` | 不变 |
| `SecurityLog` | `security_log` | 不变 |

**需求 4（推送时间任意化）建模：**
- `Strategy.push_start_time` 新增，`HH:MM` 每日循环，可空。
- 有值 → 推送时间手动指定，固定展示该时间点，不参与冲突/互斥检测，可与其它策略重叠。
- 空值 → 保持现有 normal 模式（结论后动态推导推送）。
- 甘特图始终展示推送色块（有值显示固定区间，空值显示推导区间或"结论后"）。

**需求 5（互斥）建模：**
- 不新增字段，通过 `services/mutex.py` 在保存策略时校验：同版本内另一分支构建阶段与当前构建阶段时间重叠则返回 40902 拒绝保存。

## 5. 业务逻辑

### 5.1 冲突检测重构（`services/conflict.py`）

三层检测：

| 层级 | 检测范围 | 规则 | 处置 |
|------|---------|------|------|
| 互斥检测(Mutex) | 跨分支、同版本 | 构建阶段时间重叠 → 拒保存 | 40902 硬拦截 |
| 阶段冲突 | 同分支内 | 冒烟/分析阶段与其它策略重叠（推送除外） | 40901 硬拦截 |
| 推送重叠 | 全局 | 推送时间与任何内容重叠 | 不拦截，仅甘特展示 |

### 5.2 互斥检测（`services/mutex.py`，新增）

- 输入：目标 `version_id`、`build_start_time`、模板耗时、`push_mode`。
- 逻辑：遍历同版本其它分支的启用策略，用 build_start_time + 构建耗时展开构建起止，检测与当前策略构建区间是否重叠。
- 返回：冲突的分支/策略/时段列表。
- 调用点：`create_strategy`、`update_strategy` 保存前先跑互斥 + 阶段冲突，任一命中即 40902/40901 拒绝保存。

### 5.3 推送时间推导（`services/timeline.py`）

- 有 `push_start_time` → 推送阶段固定为 `push_start_time` ~ `push_start_time + push_minutes`。
- 空值 → 保持现有 normal 模式（分析结论后动态推导，`push` 为 null）。
- 甘特图：始终展示推送色块（有值固定区间高亮；空值只在有结论时出现）。

### 5.4 甘特图优化（需求4）

- 推送色块从"结论后动态"改为"按配置时间固定展示"，与其它策略重叠时并排/叠放展示，不再标红。
- 互斥冲突的构建色块仍用红色斜纹高亮（展示历史/种子冲突数据）。

## 6. 前端页面设计

### 6.1 版本计划页优化（需求1）

**现状问题**：`plan/index.vue` 控制台报错（需定位，如 `timeToMs` 对空 push 或 `phaseKey` 解析问题）；点击色块仅 PM 可跳转，无详情。

**改动**：
- 点击甘图上任意阶段色块 → 下方展开详情面板（复用全景页样式）：
  - 策略配置：分支、模板、构建时间、推送模式、推送时间（新增）、状态
  - 时间线：构建/冒烟/分析/推送各阶段起止（来自 plan 返回的 timeline）
  - 执行历史：该策略近期 execution_round 表格（复用 getExecutions）
- 修复控制台报错：健壮性处理空 timeline/空 push、phaseKey 解析容错。
- 保留 PM 点击跳转策略编辑能力（与详情面板并存）。

### 6.2 周视图新页面（需求2）— `views/weekly/index.vue`

**布局**（四行）：
- 第一行：当前日期所在周信息（"今年第XX周，xx月xx日-xx月xx日"）+ 本月周列表下拉（第1~4周可选）+ 右侧版本选择按钮。
- 第二行：当前所选版本的分支列表标签（横向展示）。
- 第三行：核心网格——列为周一~周日，行为各分支策略按 build_start_time 从凌晨排序的排布；每格展示 `27A-Master-XX` 策略名 + 时间点，按分支配色。
- 第四行：图例——不同颜色对应的分支说明。

**实现**：自研 CSS Grid 网格组件（不依赖 ganttastic），数据来自新增接口 `GET /api/weekly?week=...&version_id=...`。

### 6.3 系统管理策略配置页（需求3）

- 在 `admin/index.vue` 新增"策略配置" Tab。
- 管理员可对 strategy 表完整 CRUD（新建/编辑/删除/启停），不受 PM 只配置本版本限制。
- 复用/抽象策略编辑表单（含新字段 push_start_time），保存时仍执行互斥 + 阶段冲突校验。
- 删除策略前确认（提示会级联清理关联执行数据）。

## 7. 新增/变更后端接口汇总

| 接口 | 说明 |
|------|------|
| `GET /api/weekly` | 周视图数据（周/日期/版本 → 分支策略排布） |
| `GET /api/plan` | 扩展：返回 push_start_time、修复推送色块 |
| `GET /api/strategies` | 扩展：返回 push_start_time |
| `POST/PATCH/DELETE /api/strategies` | 管理员完整 CRUD（现有 PM 逻辑保留，放开 admin 权限） |

## 8. 测试计划

- 后端：Django TestCase 覆盖登录/JWT、策略 CRUD、互斥检测、阶段冲突、推送推导、权限（PM 仅本版本、admin 全量）。
- 前端：编译通过、控制台无报错、各页面功能手测。
- 联调：前后端真实数据流转验证（登录→看板→周视图→策略配置→推送/互斥校验）。

## 9. 假设与边界

- 现有 FastAPI 代码保留但转换为 Django 后端时以 `backend/` 下 Django 项目为准；FastAPI 代码停用/删除由实施阶段决定。
- 周视图"本周"以周一为周起始，第1~4周为当月自然周（若当月不足4周则按实际）。
- push_start_time 为空时保持 normal 动态推导，不破坏现有执行语义。