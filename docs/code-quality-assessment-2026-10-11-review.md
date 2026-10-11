# 代码质量评估报告（复评版 + 首批修复记录）

> **评估日期**：2026-10-11
> **评估性质**：**复评**（Re-review）——本项目当日已执行「阶段 1~5」优化（提交 `4a94043`~`0fba4c9`），本报告不复述旧结论，而是**验证旧问题修复状态 + 定位优化过程中新引入/残留的问题**。
> **基线实测**：后端 `python manage.py test build_protection_service` → **150 passed, 1 skipped**（耗时 139.8s）；前端 `npm run test` → **32 passed / 5 files**；`git status` 干净。
> **代码规模**：后端 6,324 行（含测试 2,275 行，业务+配置 4,049 行）；前端业务代码 11,510 行（`src/views` 9,592 + `src/api` + `src/composables`）。
>
> ---
>
> ## ✅ 首批修复已落地（2026-10-11 上午）
>
> 本报告第六节的「第一批」已全部实施完成，验证通过：
>
> | 项 | 问题 | 状态 | 测试增量 |
> |---|---|---|---|
> | H-1 | 后端 ID 参数类型防护 | ✅ 已修复 | 后端 150 → **176 例**（新增 `tests_id_guard.py` 26 例） |
> | H-3 | 登录失败无 `.catch`，提示分支死代码 | ✅ 已修复 | 前端 typecheck 通过 |
> | H-4 | `weekly-new` 首屏重复请求 | ✅ 已修复 | — |
> | M-6 | 轮询固定 30s 无退避、错误弹窗轰炸 | ✅ 已修复 | 前端 32 → **40 例**（新增 `polling.spec.ts` 8 例） |
>
> **验证结果**：后端 176 passed(1 skipped) ✅ / 前端 40 passed(6 files) ✅ / typecheck 0 error ✅ / eslint 0 warning ✅ / build 通过 ✅
>
> ### 修复过程中发现的两处额外问题
>
> 1. **`parse_int` 存在全角数字漏洞**：Python `int("０")` 返回 0，全角数字会被当成合法 ID 放行。
>    已在 `views/__init__.py` 与 `services/slot_booking.py` 两处实现中加 `str.isascii()` 拦截，并补测试锁定
>    （`_BAD_IDS` 含 `"０"`、`"１２３"`）。
> 2. **`Version.pm_user_id` 有唯一约束**（一个 PM 只绑一个版本），此前**无测试覆盖、无文档说明**。
>    排查过程中一度误判为代码 Bug，实为测试数据设计错误。已补 `test_create_version_reuse_pm_conflicts_40902` 锁定该行为。
>    ⚠️ 这是个**隐式业务规则**，建议在 `models/others.py` 的 `Version.pm_user` 字段加注释说明。
>
> ### 修复过程中的范围修正（重要）
>
> 原报告 H-1 称「19 处裸 `filter(id=)` 可远程触发 500」。**实施时发现该说法偏宽**：
>
> - **URL 路径参数不构成风险**：`urls.py` 中所有 id 均为 `<int:vid>` / `<int:pk>` 等形式，
>   Django 的 path converter 会先做整数转换，**非数字根本不会进入视图函数**。
> - **真实风险仅来自 query/body 参数**，实际为 **9 处**：strategies(4)、admin(3)、slot_booking(3)、
>   weekly(1)、executions(1)。
>
> 修复已覆盖全部 9 处，风险点归零。

---

---

## 总体结论

**质量水位较上一版有实质性跃升。** 上一版的 1 个确定性 500 Bug、密钥泄漏、logout 失效、零测试基建等 9 项已完全修复；架构层面「写路径下沉服务层、配置落库、错误码集中、跨模块私有访问」等 P1 问题基本收敛。

**当前主要风险已从「确定性崩溃/安全事故」转为「残留一致性缺口」**，具体表现为三条主线：

1. **ID 参数类型防护只做了 1/5** —— `parse_int` 工具已建好，但仅 `branch_config.py` 一个模块在用，其余 4 个模块（strategies / admin / slot_booking / weekly）仍是裸 `filter(id=<未校验>)`，实测会抛 `ValueError` → **HTTP 500**。
2. **策略互斥校验仍是纯 check-then-act** —— 同一项目内 `SlotBooking` 与 `RunningInstance` 都已用「`UniqueConstraint` + `IntegrityError`」做了并发兜底，唯独核心的 `Strategy` 模型没有，导致「正确范式没有推广到最关键的地方」。
3. **前端「收敛」只做了 60%** —— `constants.ts` 已建但 `execution/panorama` 仍在本地重复定义映射；`branch-config` 的 5s 轮询缺过期响应守卫（同一项目 `weekly` 页已有成熟范式，同样没推广）。

**评级：中高（72/100）** —— 无 P0 级阻断问题，剩余问题集中、可控，且多数有现成范式可就地复制。

---

## 一、旧问题修复验证表（后端）

| # | 旧问题 | 状态 | 证据 |
|---|---|---|---|
| 1 | 删除被引用模板必然 500 | ✅ 已修复 | `views/admin.py:296` 改为捕获 `ProtectedError`（`from django.db.models import ProtectedError`，`:5`），返回 40903 |
| 2 | `.env` 含真实密钥被 git 追踪 | ✅ 已修复 | `git ls-files \| grep env` 仅返回 `.env.example`；`.gitignore:19` 已含 `.env` |
| 3 | HH:MM 校验放行 `"99:99"` | ✅ 已修复 | `services/timeline.py:14-19` `valid_hhmm()` 增加数值范围断言；`services/strategies.py:39-41` 前置校验并抛 42201 |
| 4 | 一组不安全默认值 | ✅ 已修复 | `settings.py:13` DEBUG 默认 false、`:108` CORS 默认 false、`:102-103` JWT 签名密钥独立于 SECRET_KEY；`AGENTS.md` 已固化约定 |
| 5 | logout 形同虚设 | ✅ 已修复 | `views/login.py:52-74` 解析 Bearer → 写 `RevokedToken` 黑名单；`:34-37` 连续失败 5 次锁定 15 分钟（`42901`） |
| 6 | 策略互斥校验无并发兜底 | ❌ **未修复** | `models/others.py:75-76` Strategy.Meta 仅 `ordering`，无 `UniqueConstraint`；`views/strategies.py` 与 `services/strategies.py` 均无 `IntegrityError` 捕获 |
| 7 | 运行期配置是假持久化 | ✅ 已修复 | `services/config.py` 改为 `RuntimeConfig` 表 + 进程内缓存，`set_config` 落库（`models/others.py:147` `key` 唯一） |
| 8 | 魔法日期 `"2026-08-10"` 散布 | ✅ 已修复 | 全库扫描零命中；`services/strategies.py:46`、`views/strategies.py:91` 统一为 `timezone.localdate()` |
| 9 | 权限体系双轨制 | ✅ 已修复 | `cc9656b` 删除零引用 `permissions.py`；`views/__init__.py:35-39` `require_admin` 成为唯一 admin 门槛实现 |
| 10 | 错误处理散乱 | ⚠️ **部分修复** | `errors.py:14-38` 常量与 `CODE_STATUS` 映射已成唯一真源、`fail_resp` 统一出口；但 **`admin.py` 内 28 处仍写裸数字** `fail_resp(42201,…)`；`first_error`/`_fmt` 已收敛到 `views/__init__.py:25,42` |
| 11 | 读路径写副作用 + N+1 | ⚠️ **部分修复** | N+1 已用 `select_related`/`prefetch_related` 解决；但 **`views/branch_config.py:226` GET 请求仍调 `advance(inst)` 写库**（docstring 自认「读取时推进状态」） |
| 12 | 跨模块访问私有成员 | ✅ 已修复 | `views/admin.py:10-15` 正常 import 服务层；`_create_admin_strategy` 已复用 `svc_create_strategy`（`:412`） |
| 13 | `ReportRevisionLog.report_id` 无索引 | ✅ 已修复 | `models/report.py:46` `db_index=True` |
| 14 | `weekdays` 未校验 / 非数字 ID 500 | ⚠️ **部分修复** | `serializers/slot_booking.py:29-38` `validate_weekdays` 已补；ID 防护见本报告 H-1（**未修复且扩散**） |
| 15 | `release` 忽略 `is_valid()` | ✅ 已修复 | `views/slot_booking.py:88,109,147,165` 四处均已判 `is_valid()` |
| 16 | 分支关联无事务 | ✅ 已修复 | `models/branch_config.py:39` `unique_together = ("branch","project")` + `admin.py` 捕获 `IntegrityError` |

---

## 二、后端问题清单（本次新发现）

### 🔴 高危

#### H-1　ID 参数未做类型防护，非法 ID 直接 500（12 处调用点）

**实测证据**（Django 5.2.4）：

```
filter(id='abc')      -> ValueError: Field 'id' expected a number but got 'abc'.
filter(id='1; DROP')  -> ValueError: Field 'id' expected a number but got '1; DROP'.
filter(id='')         -> ValueError: Field 'id' expected a number but got ''.
```

`views/__init__.py:47-52` **已经写好了** `parse_int()` 安全转换函数，docstring 明确写着「避免 ValueError 500」——但全库只有 3 处在用：

| 已防护 ✅ | 未防护 ❌ |
|---|---|
| `views/branch_config.py:107,164,201` | `views/strategies.py:74,75,102,103`（4 处）<br>`views/admin.py:59,94,104,127,188,260,409,410,442,455,465`（11 处）<br>`services/slot_booking.py:181,199,200`（3 处）<br>`views/weekly.py:33`、`views/executions.py:56,72`、`views/login.py:68` |

**影响**：
- **可远程触发 500**：任何已登录用户（含最低权限 `tester`）向 `/api/strategies` POST `{"branch_id":"abc"}`，即在 `views/strategies.py:102` 抛出未捕获 `ValueError`，Django 返回 HTML 500 页面 —— **破坏 `{code,message,data}` 统一契约**，前端 `BizError` 拿不到 `code`，只能落到通用兜底。
- `views/weekly.py:33` 与 `views/executions.py:56,72` 走 URL 路径参数，外部可达性最强。
- 该文件仅 3 处被加固，说明**防护是「想到哪补到哪」而非系统性约束**，新增端点必然重犯。

**建议**：
1. 短期：上述 19 处统一包 `parse_int(...)`；`filter(id=None)` 虽不报错但会返回「无结果」，需显式判空并返回 40401/42201。
2. 根治（推荐）：实现一个 `get_object_or_404_safe(Model, **kw)` 助手，或给 `parse_body` 配套的 `require_int(body, key)`，并在 `views/urls.py` 层加统一异常中间件兜底 `ValueError → 42201`，使「契约破坏」不可能发生。

#### H-2　策略互斥校验缺少并发兜底，可产生互相冲突的策略

**位置**：`models/others.py:75-76`、`services/strategies.py:119-129`、`views/strategies.py:109-118`

`services/strategies.py:119` 虽有 `@transaction.atomic`，但 `validate_strategy`（`:48-74`）是「先查后写」，且 `Strategy` 模型**无任何唯一约束**可兜底。同一版本下两个 PM 并发提交冲突策略时，两个事务都可能通过校验并成功落库。

**同一项目内的正确范式已存在两处，唯独核心策略没采用**：

| 模型 | 并发兜底 | 位置 |
|---|---|---|
| `SlotBooking` | ✅ `UniqueConstraint(fields=["date","template"], condition=Q(status="reserved"))` + `IntegrityError→40904` | `models/slot_booking.py:73-78`、`services/slot_booking.py:206-228` |
| `RunningInstance` | ✅ `UniqueConstraint(fields=["branch_project"], condition=Q(status__in=("STARTING","RUNNING")))` | `models/branch_config.py:125-130` |
| **`Strategy`** | ❌ **无约束、无 IntegrityError 捕获** | `models/others.py:75-76` |

**影响**：构建互斥是本系统的**核心业务约束**（同一时间节点仅允许一个分支构建）。一旦被绕过，会出现两个分支同一时刻构建、CI 资源争抢；且因为没有 DB 约束，这种脏数据**事后无法自动检出**。

**建议**：
- 中期可行：为「同一分支同一构建时间」加 `UniqueConstraint(fields=["branch","build_start_time"], condition=Q(enabled=True), name="uniq_active_strategy_time")`，并捕获 `IntegrityError→40902`。注意跨分支互斥（`check_build_mutex` 是跨分支的）无法用简单唯一约束表达，需依赖**显式表锁**（`select_for_update` 锁 Version 行）或**串行化校验队列**。
- 至少先在文档/spec 中明确标注该限制，并在 UI 上对「并发提交」给出提示。

### 🟡 中危

#### M-1　GET 请求写数据库，违反 REST 语义且阻塞读取

**位置**：`views/branch_config.py:212-235`（docstring 第 214 行自认「读取时推进状态」），第 `226` 行 `advance(inst)`

**影响**：
- GET 不幂等：单纯刷新页面就会修改数据库；被爬虫/预取器反复 GET 会持续推进实例状态机。
- 写操作发生在读取循环内且**无事务**：`latest_instances_for_branch` 查完 → 循环内逐个 `advance` 写库，中途异常导致状态推进了一半。
- 前端 `branch-config/index.vue:216-223` 有 **5s 轮询**（对比 `execution` 页 30s），意味着**每 5 秒对每个活跃实例执行一次 UPDATE** —— 写放大了 6 倍。

**建议**：改为 POST `/branch-projects/<pk>/instances/<iid>/advance`，或把状态推进移到定时任务（`django-q`/管理命令），GET 只读。若保留现状，至少包 `transaction.atomic` 并把轮询间隔调到 15s+。

#### M-2　`admin.py` 28 处裸魔法错误码，与 `errors.py` 的「唯一真源」设计自相矛盾

**位置**：`views/admin.py:56,58,61,64,68,84,96,101,106,110,115,129,133,135,139,164,166,168,175,178,190,198,212,225,239,249,262,311,344` 等

`errors.py:26` 注释写着「业务码 → HTTP 状态映射：视图组装响应时的唯一真源」，但 `admin.py` 直接写 `fail_resp(42201, …)` 而非 `fail_resp(CODE_UNPROCESSABLE, …)`。

**影响**：新增/调整错误码语义时（如把 42201 拆细）需 grep 数字字面量，`admin.py` 里 28 处会漏改；`fail_resp` 的 `CODE_STATUS.get(code, 400)` 兜底也使「拼错码不会报错，只会静默返回 400」。

**建议**：`from ..errors import *` 或显式导入常量，全量替换为常量名。`views/slot_booking.py` 内部还有一份 `_err` + `_ERR_STATUS` 私有映射（`services/slot_booking.py:33-36` 注释称已收敛，实际 `_err` 仍在本文件），也应改为直接调用 `fail_resp`。

#### M-3　多端点固定 200 条截断，无分页

**位置**：`views/admin.py:361,373`、`views/executions.py:49`、`views/logs.py:11,24`（共 5 处 `[:200]`）；`settings.py:96` `"DEFAULT_PAGINATION_CLASS": None`

**影响**：日志表是最容易持续增长的表（执行日志、变更日志）。第 201 条以后的记录**永久无法通过 API 访问**，无任何提示。运维排查问题时拿不到历史数据。

**建议**：至少给日志类端点加 `?page=&page_size=` 参数；对确实只需最近 N 条的场景，在响应里返回 `truncated: true` 让前端明示。

### 🟢 低危

| # | 问题 | 位置 | 建议 |
|---|---|---|---|
| L-1 | 安全日志 `detail` 恒为空，审计价值接近零（登录失败/成功/锁定 4 处均未传 detail，无 IP、无 UA） | `views/login.py:39,44,50,74`；`views/__init__.py:55-58` 已支持 `detail` 参数但无人使用 | 补 `request.META.get("REMOTE_ADDR")` 与 User-Agent，`security_log` 调用点补第三个参数 |
| L-2 | `_admin_log` / `security_log` 裸 `except Exception` 仅打 warning，审计写入失败静默 | `views/admin.py:33`、`views/__init__.py:59` | 注释已说明「审计旁路不阻断业务」，属合理设计；但建议 `logger.exception` 保留堆栈，否则无法排查 |
| L-3 | `validate_strategy` 内 `from django.conf import settings` 局部导入 + `push_start_time=None` 时 `detect_conflicts` 行为未显式说明 | `services/strategies.py:36,71` | 局部导入是性能优化，可接受；建议补一行注释说明 `push_start_time` 为空时走 `push_mode` 分支 |
| L-4 | `SimpleNamespaceTpl` 鸭子类型替身，绕过 ORM 但无类型约束 | `services/strategies.py:25-30` | 注释已说明理由；若后续 `detect_conflicts` 依赖更多模板字段，易静默失配。建议改用 `@dataclass` 或 `SimpleNamespace` 标注字段名 |
| L-5 | `Strategy.build_start_time` 用 `CharField` 存 `"HH:MM"` | `models/others.py:63-65` | 字符串存储便于排序但无法做时间范围查询。当前规模可接受，建议加注释说明取舍 |
| L-6 | `User.role`（小写）与 `BranchPermission.role`（大写 VIEWER/OPERATOR/ADMIN）双命名体系 | `models/others.py`、`models/branch_config.py` | 两套语义不同但命名易混；建议至少在 `models/branch_config.py` 加注释区分 |

---

## 三、前端问题清单

### 旧问题修复验证

| # | 旧问题 | 状态 | 证据 |
|---|---|---|---|
| 1 | `tsconfig.json` `strict: false` | ❌ **未修复** | `tsconfig.json:6` `"strict": false`、`:7` `"strictFunctionTypes": false` |
| 2 | `no-explicit-any: off` | ❌ **未修复** | `eslint.config.js:81`（另 `:84` `no-non-null-assertion`、`:154` `vue/no-v-html` 也关闭） |
| 3 | 生产启用 mock | ✅ 已修复 | `build/plugins.ts:48` `enableProd: false` |
| 4 | 登录页硬编码口令 | ⚠️ 收紧为 DEV | `login/index.vue:41-42` `import.meta.env.DEV ? "admin" : ""` |
| 5 | API 错误契约不统一 | ✅ 已修复 | `api/http.ts:10-22` `BizError`；全库业务侧已无 `e?.response?.data?.code` 深取 |
| 6 | 401 不清业务身份 | ✅ 已修复 | `api/http.ts:39-45` `clearBusinessUser()`，`:68` 调用；单测覆盖 `http.spec.ts:70-77` |
| 7 | `types.ts` 状态/角色为 `string` | ✅ 已修复 | `api/types.ts:15-33` 已定义 `Role`/`PushMode`/`PushStatus`/`ReportStatus` 等字面量联合 |
| 8 | `BranchItem` 双定义 | ✅ 已修复 | 唯一定义 `api/branchConfig.ts:11`；`api/types.ts:133` 改名 `BranchBriefItem` 并注释区分 |
| 9 | `report/detail.vue` 超大 | ⚠️ 部分 | 现 1006 行（旧 1081），逻辑已抽出，模板+样式仍占 596 行 |
| 10 | `admin/index.vue` 超大 | ✅ 已修复 | 810 行 → **76 行**，拆为 5 个 Tab 子组件 |
| 11 | `el-switch` 乐观更新不回滚 | ✅ 已修复 | `strategy/index.vue:251-255,170-179`、`slot-config/index.vue:64-69`、`admin/components/StrategiesTab.vue:136-145` 均改为 `:model-value` + 操作后重载 |
| 12 | UTF-8 BOM | ✅ 已修复 | 全量扫描 0 命中 |
| 13 | 轮询无退避/隐藏不暂停 | ⚠️ 部分 | `execution/index.vue:113-114` 已加 `document.hidden` 暂停；`:112` 仍固定 30s 无退避 |

### 🔴 高危

#### H-3　`login/index.vue` 登录失败无 `.catch`，错误提示分支是死代码

**位置**：`src/views/login/index.vue:55-71`

```ts
.then(res => { if (res.success) {...} else { message("登录失败", …) } })
.finally(() => (loading.value = false));   // ← 无 .catch
```

`loginApi` 失败时 http 层 reject `BizError`（`api/http.ts:86`），`.then` 被整体跳过。后果：(a) 控制台 Unhandled Promise Rejection；(b) `:68` 的 `message("登录失败")` **永远不会执行**；(c) 该 Promise 源自 `el-form.validate(valid => {...})` 回调（`:47`），无人 await，异常无声消散。

**建议**：在 `.then` 与 `.finally` 之间插 `.catch(() => message("登录失败，请检查账号密码", { type: "error" }))`，并删除 `.then` 中的 `else` 分支（职责重叠）。

#### H-4　`weekly-new/index.vue` setup 顶层裸调异步函数，首屏重复请求

**位置**：`src/views/weekly-new/index.vue:383-384`

`loadWeekly()` 内部（`:214-216`）会写 `versionId.value`，触发 `:332-334` 的 `watch(versionId)` 二次调用 `loadWeekly()` —— **首屏必然请求两次**。且这两行未 await 也不在 `onMounted` 内，`loadCalendar` 的 catch（`:229-231`）为空。

**建议**：改为 `onMounted(async () => { await Promise.all([loadWeekly(), loadCalendar()]) })`，并在 watch 中加初始化守卫。

### 🟡 中危

#### M-4　`pushStatusMap` / `conclusionMap` 三份副本，文案已不一致

| 位置 | failed 文案 |
|---|---|
| `src/views/constants.ts:45`（权威） | `"失败"` |
| `src/views/execution/index.vue:142` | `"推送失败"` |
| `src/views/panorama/index.vue:111` | `"失败"` |

`constants.ts:41-51` 已导出 `pushStatusMap` + `pushStatusMeta`、`:10-18` 导出 `roundConclusionMap` + `roundConclusionMeta`，但这两个页面**一个都没用**。后端新增推送状态需改 3 处。

**建议**：`execution/index.vue:132-144` 与 `panorama/index.vue:107-118` 删除本地定义，改 import `views/constants`；模板中 `(pushStatusMap[row.push_status] || …).type` 改为 `pushStatusMeta(row.push_status).type`。

#### M-5　`branch-config` 5s 轮询无过期响应守卫，切分支写入脏数据

**位置**：`src/views/branch-config/index.vue:216-223`

用户在 A 分支的 `getBranchInstances` 在途时切到 B 分支，`watch(selectedId)`（`:225-234`）只重启定时器、**不作废在途请求**。若 A 的响应晚于 B 返回，`instanceRows` 会被写成 A 分支实例，而标题显示 B 分支。

**同一项目的正确范式就在隔壁**：`weekly/index.vue:14,138,146,150` 已实现模块级 `let seq = 0` + `const cur = ++seq` + await 后 `if (cur !== seq) return`。

**建议**：照抄该模式，并在 `watch(selectedId)` 开头 `seq++` 主动作废。

#### M-6　`execution/index.vue` 轮询失败无退避，形成错误弹窗轰炸

**位置**：`src/views/execution/index.vue:112-115` `load().catch(() => {})` + 固定 30000ms

空 catch 只挡 rejection，**挡不住 toast** —— `api/http.ts:84` 的错误拦截器无条件弹 `ElMessage.error`。后端持续 500 时，用户每 30 秒被弹一次错误，无法关窗。同时 `loading`（`:61,67`）每轮被置 true/false，表格 `v-loading`（`:163`）每 30s 闪一次遮罩。

**建议**：加失败计数，连续失败 ≥3 次转指数退避（30s→60s→120s，上限 5min），首次失败才 toast，后续静默；轮询路径改用独立 `refreshing` 标志，不复用 `loading`。

#### M-7　`BRANCH_PALETTE` 配色方案在 weekly 与 weekly-new 完整复制

**位置**：`src/views/weekly/index.vue:93-111` 与 `src/views/weekly-new/index.vue:165-205`

6 色板数组、`Map` 构建、`(idx+1) % length` 取色三段逐行重复，且收尾符不同（`||` vs `??`）。改配色需同步两处，遗漏会导致同一分支在两个页面显示不同颜色。

**建议**：抽 `useBranchColors(branches)` 到 `src/composables/`，统一用 `??`。

#### M-8　`StrategyForm.push_mode` 未复用已定义的 `PushMode` 字面量联合

**位置**：`src/api/strategy.ts:11` `push_mode: string`（应为 `PushMode`）

`types.ts:17` 已定义 `PushMode = "normal" | "sync"`，但表单层是类型盲区 —— `"Normal"` / `"NORMAL"` / 空串都能通过编译进入请求体，被后端 42201 拒绝。属优化过程中的**收敛遗漏**：`StrategyItem.push_mode` 改了，`StrategyForm.push_mode` 漏了。

**建议**：改为 `push_mode: PushMode` 并 import 类型。

#### M-9　`strategy/index.vue` 直接裸调 `http.get("/admin/templates")` 绕过 API 层

**位置**：`src/views/strategy/index.vue:92`

PM 角色页面请求 `/admin/*` 管理端路径（越权依赖后端拦截），且 `as TemplateItem[]` 断言绕过了解包契约，失败时走 `:93-106` 的降级 hack（`smoke_minutes`/`analysis_minutes` 硬编码为 `0`，导致预览时间线失真）。

**建议**：后端补一个 PM 可读的只读 `/templates` 端点，前端在 `api/` 增加 `getTemplates()`。

### 🟢 低危

| # | 问题 | 位置 | 建议 |
|---|---|---|---|
| L-7 | `report/index.vue` 与 `detail.vue` 版本/策略级联下拉逻辑完整重复，且策略未按 name 去重 | `report/index.vue:37-53`、`report/detail.vue:90-104` | 抽 `useVersionStrategyOptions` 到 composables |
| L-8 | 剪贴板降级逻辑重复且 `execCommand` 返回值未检查，可能「假成功」 | `report/detail.vue:351-363`、`report/index.vue:75-89` | 抽 `copyText(): Promise<boolean>`，检查返回值 |
| L-9 | `execution/index.vue` 模板 6 处 `as RoundItem` 断言 + 同一表达式重复调用两次 | `execution/index.vue:175,183,191,200,204,205` | 抽 `ExecutionTable.vue` 子组件 |
| L-10 | `welcome/index.vue` 仍是 pure-admin 模板占位页，但已注册为登录后默认首页 | `welcome/index.vue`（88 行）、`router/modules/home.ts:16-18` | 改为业务落地页（复用 `execution/index.vue:31-57` 的 stats 计算） |
| L-11 | mock 内硬编码假 JWT | `mock/login.ts:20-21,34-35`、`mock/refreshToken.ts:13-14` | 加注释「仅开发，enableProd 必须保持 false」 |
| L-12 | `mock/login.ts` / `refreshToken.ts` 与 `branch-config` 轮询问题叠加时，`business.ts` 导出已全部在用 | `utils/business.ts` | ✅ 无需处理（旧报告误判为死代码） |

---

## 四、做得好的方面（保持）

- **写路径服务层收敛彻底**：`services/strategies.py` + `views/__init__.py` 的 `fail_resp`/`first_error`/`require_admin`/`fmt_dt`/`parse_int`/`parse_body`/`authed_user` 已成唯一实现，PM 与 admin 两入口真正共用同一套校验与响应组装。
- **配置真持久化**：`RuntimeConfig` 表 + 进程内缓存，`set_config` 落库且写时刷新缓存；docstring 诚实说明「单机部署足够，跨进程强一致需求出现时再引入共享缓存」——这种**明确技术债边界**的注释方式值得推广。
- **并发正确范式**：`SlotBooking`（条件唯一约束）与 `RunningInstance`（条件唯一约束）两处模型设计是全库最佳实践，附带并发测试。
- **时间线推导单一真源**：`services/timeline.py` 的 `build_timeline` + `valid_hhmm` 被 preview、mutex、conflict 三处共用，且 `check_build_mutex:62-64` 对单条脏数据策略做了 try/except 降级跳过 + warning，不会因一条坏数据整体 500。
- **前端类型收敛有实效**：`types.ts` 字面量联合、`useStrategyPreview` 防抖 + seq 过期守卫、`admin/index.vue` 810→76 行、`BOM` 全清、`el-switch` 回滚模式统一。
- **测试基建从零建成**：后端 150 例、前端 32 例，`http.spec.ts` 锁定 BizError 全错误码路径，`contract.spec.ts` 锁定 URL/方法拼装。

---

## 五、量化指标对比

| 指标 | 旧基线（10-11 优化前） | 当前（复评） | 变化 |
|---|---|---|---|
| 后端测试 | 114 例（1 skip） | **150 例（1 skip）** | +32% ✅ |
| 前端测试 | 0 | **32 例 / 5 files** | 从零建成 ✅ |
| 前端业务 `any` | 大量 | **4 处**（`src/views/`） | ✅ 大幅收敛 |
| UTF-8 BOM | 5 个文件 | **0** | ✅ |
| `admin/index.vue` | 810 行 | **76 行** | −91% ✅ |
| 生产 mock | 启用 | **关闭** | ✅ |
| `.env` git 追踪 | 是（密钥泄漏） | **否** | ✅ |
| 后端裸魔法错误码 | 散落全库 | **集中于 admin.py 28 处** | ⚠️ 未清尾 |
| ID 类型防护 | 0 处 | **3 处**（工具已建但未推广） | ⚠️ 未推广 |
| 模型并发约束 | 1 处 | **2 处**（Strategy 仍缺） | ⚠️ 核心缺口 |
| 业务重复逻辑处数 | 约 8 处 | **5 处** | ⚠️ 收敛 60% |
| `tsconfig strict` | false | **false** | ❌ 未动 |

---

## 六、优先级排序与建议路线

### 第一批（1~2 天，建议立即做）

| 序 | 问题 | 位置 | 理由 |
|---|---|---|---|
| 1 | **H-1** ID 参数统一 `parse_int` + 全局异常兜底 | 后端 19 处调用点 | 唯一可远程触发 500 的入口，且工具已现成，改动机械 |
| 2 | **H-3 / H-4** 前端登录 `.catch` 补齐、`weekly-new` 初始化去重 | `login/index.vue:55-71`、`weekly-new/index.vue:383-384` | 影响登录主链路与首屏性能，改动 < 10 行 |
| 3 | **M-6** 轮询退避 + 错误去重 | `execution/index.vue:112-115` | 后端故障时用户体验崩塌，且改动局部 |

### 第二批（3~5 天）

| 序 | 问题 | 位置 | 理由 |
|---|---|---|---|
| 4 | **M-1** GET 副作用改为显式写端点 | `branch_config.py:212-235` + 前端 `branch-config/index.vue` | REST 语义 + 5s 写放大，需前后端联动 |
| 5 | **M-5 / M-7** 前端 seq 守卫 + 配色收敛 | `branch-config/index.vue:216-223`、`weekly*/` | 范式已存在（`weekly/index.vue:14`），照抄即可 |
| 6 | **M-2** admin.py 错误码常量化 | `admin.py` 28 处 | 纯机械替换，建议与 1 同批做（都在后端） |
| 7 | **M-4** constants.ts 映射真正落地 | `execution/index.vue`、`panorama/index.vue` | 与 5 同批，顺手统一文案 |

### 第三批（1 周内，需设计评审）

| 序 | 问题 | 说明 |
|---|---|---|
| 8 | **H-2** 策略互斥并发兜底 | 跨分支互斥无法用简单唯一约束表达，需设计决策（Version 行锁 / 串行化队列 / 物化冲突表），**建议先写 spec 再动手** |
| 9 | **M-3** 日志端点分页 | 影响运维能力，需前后端协议约定 |
| 10 | 低危项 L-1~L-12 | 可随手清理，`welcome` 页改造与 `report/detail.vue` 拆分可合并做 |

### 单独决策项：前端类型闸门

`tsconfig.json` `strict:false` + `eslint` 三条规则关闭（`no-explicit-any` / `no-non-null-assertion` / `vue/no-v-html`）——**不建议直接开 `strict`**（基座 pure-admin 代码未适配，开关即上百个错误），但建议**先只改 ESLint**：`no-explicit-any` 从 `off` 改 `warn`，配合已有的 `--max-warnings 0` 暴露存量、用新代码零容忍的方式渐进收敛。这是低风险高收益的一步。

---

## 七、整体可维护性评价

**评级：良好（7.5/10）**

| 维度 | 评分 | 说明 |
|---|---|---|
| 代码结构与模块划分 | 8.5/10 | 后端三层（views/services/models）+ 领域拆分清晰，services 层职责单一；前端 api/composables/constants 层次分明。扣分点：`views/admin.py`（495 行）承担了版本/用户/模板/配置/日志/策略六类端点，是唯一的大文件 |
| 命名与编码规范 | 8/10 | 中文 `verbose_name`、中文注释、常量命名规范、commit 遵循中文 conventional commits。扣分点：`User.role` 与 `BranchPermission.role` 双命名体系；前端裸魔法错误码 |
| 错误处理与健壮性 | 7/10 | 统一响应契约 + 错误码常量 + `fail_resp` 出口设计优秀，但 **ID 类型防护推广失败（19 处裸用）** 与 2 处裸 `except Exception` 是实打实的缺口 |
| 潜在 bug 与安全 | 7.5/10 | 无已知确定性崩溃 Bug、密钥泄漏已堵、权限体系已清理。扣分点：H-1（可远程 500）、H-2（核心业务约束无并发兜底） |
| 性能 | 7.5/10 | N+1 已用 `select_related`/`prefetch_related` 系统性解决；扣分点：GET 写副作用 + 5s 轮询放大写、日志端点 200 条硬截断无分页 |
| 重复与可重构 | 7/10 | 后端重复基本收敛（唯一真源化）；前端 5 处重复（映射/配色/级联/剪贴板/断言） |
| 测试保障 | 8/10 | 后端 150 例含并发用例，前端 32 例锁定契约。扣分点：前端仍是"按文件补测"而非"按风险补测"，`branch-config`/`execution` 这类轮询密集页零覆盖 |

**核心判断**：该项目已从「分层意识好但缺乏工程约束」进化为「**有明确工程约束且大部分已落实**」。当前主要矛盾不是「不知道该怎么写」，而是「**约束没有强制力**」——`parse_int` 造好了却没人用、`constants.ts` 建好了却没人 import、seq 守卫范式写好了却只在一个页面用。这说明优化是「点状修复」而非「机制拦截」。

**建议的机制性改进**：把上述约定从「文档 + 代码评审」升级为「**lint 规则 + 自定义检查**」，例如：
- 自定义 ESLint 规则禁止 `filter(id=` 直接接收未校验变量；
- 在 `views/__init__.py` 提供 `int_arg()` 并在 `tests.py` 加一条 meta-test，断言「所有新增端点的 id 参数都经过 `parse_int`」；
- CI 中固定跑「`grep -rn "fail_resp(4" | grep -v CODE_` 应为空」的断言。

这三条落地后，本报告中 H-1、M-2 类问题将**不可能再复发**。

---

*本报告基于实际代码阅读 + 实测验证（150 例后端测试、32 例前端测试、Django ORM 异常行为探针）。所有问题均标注精确 file:line，验证结论可通过 git 提交 `4a94043`~`0fba4c9` 复现。*
