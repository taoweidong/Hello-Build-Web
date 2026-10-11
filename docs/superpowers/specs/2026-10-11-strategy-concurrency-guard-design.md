# 策略互斥并发兜底设计（H-2）

> 日期：2026-10-11
> 来源：代码质量复评报告 `docs/code-quality-assessment-2026-10-11-review.md` 高危项 H-2
> 状态：已实施

## 1. 问题

`services/strategies.py` 的策略创建/更新是 **check-then-act**：`validate_strategy` 先查同版本其它启用策略的构建区间，无重叠才写入。整个流程虽包在 `@transaction.atomic` 中，但 SQLite 默认 `BEGIN`（DEFERRED）模式下**校验读发生在取写锁之前**，两个 PM 并发提交冲突策略时可同时通过校验并先后落库 —— 构建互斥（本系统核心约束）被绕过，且事后无法自动检出。

对照：`SlotBooking`（时段抢占）与 `RunningInstance`（运行实例）均有条件唯一约束 + `IntegrityError` 兜底，唯独 `Strategy` 没有。

## 2. 关键技术事实（实测确认）

| 事实 | 证据 |
|---|---|
| Django 5.2 SQLite 默认事务是 `BEGIN`（DEFERRED），写锁在第一条写语句才获取 | `django/db/backends/sqlite3/base.py:330` |
| Django 原生支持 `OPTIONS: {"transaction_mode": "IMMEDIATE"}`，事务以 `BEGIN IMMEDIATE` 打开，进入即取 RESERVED 写锁 | 同上 `:332`、`transaction_modes = frozenset(["DEFERRED","EXCLUSIVE","IMMEDIATE"])`（`:144`） |
| **测试库行为 ≠ 生产库行为**：Django 测试库是 shared-cache 内存库（`file:memorydb...cache=shared`），并发写直接抛 `database table is locked`（SQLITE_LOCKED，不走 busy 等待）；生产磁盘文件库走 `SQLITE_BUSY` → busy_timeout 等待 | 实测探针两次复现 |
| SQLite 的 `select_for_update` 为 no-op（后端 `has_select_for_update=False`），**不能**用于本项目做行锁 | Django 文档/sqlite3/features.py |

推论：
- 配置 IMMEDIATE 后，生产环境「校验读 → 写入」整体串行：B 事务的 BEGIN 会阻塞到 A 提交，B 的校验读必然看到 A 的结果 → 冲突被校验层拦截（40901/40902）。
- 该行为**无法在现有测试基建中做并发断言**（shared-cache 直接报锁错，不走等待路径），只能靠约束兜底测试 + 部署约定保障。

## 3. 方案：三层防御

### 第 1 层：事务串行化（消除竞态窗口）

`config/settings.py` 的 DATABASES 增加一行：

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "build_strategy.db",
        # 事务以 BEGIN IMMEDIATE 打开：进入事务即取写锁，杜绝
        # 「校验读发生在他人提交前、写入发生在他人提交后」的
        # check-then-act 竞态（影响策略互斥/时段抢占等全部写路径）。
        # 迁移 PostgreSQL/MySQL 时删除本项，改在服务层用 select_for_update。
        "OPTIONS": {"transaction_mode": "IMMEDIATE"},
    }
}
```

**副作用评估**：所有 `atomic` 块进入即持 RESERVED 锁至提交。本项目 atomic 仅用于短写路径（无长事务/无事务内外呼），锁持有时间为毫秒级，可接受。若未来出现长事务需重新评估。

### 第 2 层：DB 约束（纵深防御，不依赖部署形态）

同分支同构建时刻的启用策略在业务上必然冲突（`build_minutes` 相同则构建区间必重叠），可用唯一约束表达：

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=["branch", "build_start_time"],
            condition=models.Q(enabled=True),
            name="uniq_active_strategy_branch_time",
        ),
    ]
```

覆盖 create 与 update（改 `build_start_time` 同样受约束约束）。

**范围说明**：跨分支互斥（`check_build_mutex` 检查的区间重叠）无法用等值唯一约束表达，第 1 层串行化是它的唯一防线 —— 这也是 IMMEDIATE 配置不可省略的原因。

### 第 3 层：服务层捕获 IntegrityError → 40902

`services/strategies.py` 的 `create_strategy` / `update_strategy` 在 atomic 内捕获 `IntegrityError`，转 `StrategyValidationError(CODE_DUPLICATE, ...)`，视图层已有 `_validation_error` 映射为 HTTP 409。

**实施中发现的新漏洞（已一并修复）**：`toggle_strategy`（PM 启停策略）此前直接 `s.save()`，无任何约束捕获 —— 两条同刻策略先后停用再先后启用时，第二条启用会 IntegrityError → **500**。已在 `views/strategies.py` 补捕获返回 40902。

**后续补齐（2026-10-11/12）**：admin 路由的策略启停（系统管理页 `_toggle_admin_strategy`）同样补 IntegrityError → 40902「无法启用」兜底；两处 toggle 的写库均包在 `transaction.atomic()` 子事务中执行，约束冲突时不污染外层事务（否则 SQLite/PostgreSQL 下外层事务进入 aborted 状态，后续查询全部报错）。

**SQLite 消息行为（实测）**：SQLite 的 `IntegrityError` 消息格式为
`UNIQUE constraint failed: <table>.<col1>, <table>.<col2>`，**不包含约束名**
（PostgreSQL 会含约束名）。因此兜底匹配按字段组合
（`"strategy.branch_id" in msg and "build_start_time" in msg`）而非约束名；
`Strategy` 表唯一约束仅此一个，字段组合可精确定位。
迁移 PostgreSQL 后此判断依然成立（消息含表名列名），无需改动。

## 4. 迁移注意事项（SQLite → PostgreSQL/MySQL）

| 机制 | SQLite | PostgreSQL/MySQL |
|---|---|---|
| IMMEDIATE 串行化 | ✅ 本方案 | ❌ 删除配置；改在 `validate_strategy` 前对 `Version.objects.select_for_update().get(pk=version_id)` 取行锁 |
| 条件唯一约束 | ✅ 支持 | ✅ PG 原生；MySQL 8 需改用生成列或应用层兜底 |

## 5. 测试策略

- 约束兜底：ORM 直接绕过服务层插入冲突行（模拟校验层失效），DB 层 IntegrityError。
- update 触发 mutex：已有启用策略 A(22:00)，将策略 B 的 build_start_time 改为 22:00 → 40902
  （**实测确认行为链**：同分支同时刻冲突由 mutex 层——构建区间重叠检测，同版本下含同分支——
  以 40902 拦截；detect_conflicts(40901) 只管 smoke/analysis 阶段重叠）。
- toggle 启用撞约束：两条同刻策略停用后先后启用，第二条 409 而非 500。
- 正常路径回归：合法创建/更新/停用后释放坑位不受影响。
- 并发行为本身：受测试基建（shared-cache 内存库）限制不做线程级断言，
  以第 2 层约束 + 第 1 层配置（生产文件库语义）覆盖（见第 2 节推论）。

## 6. 影响

- `config/settings.py`（+3 行）
- `models/others.py`（+1 约束）、新增 migration
- `services/strategies.py`（create/update 各 +4 行捕获）
- 新增测试约 4 例
