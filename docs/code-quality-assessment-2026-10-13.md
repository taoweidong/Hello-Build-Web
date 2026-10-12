# 代码质量评估报告（2026-10-13，第三轮全库复评）

> 评估范围：`backend/`（Django 5 + DRF + SimpleJWT + SQLite，业务代码约 1.0 万行）与 `frontend/src`（Vue 3 + Vite + TS + Element Plus，pure-admin-thin v6.2.0，业务代码约 2.6 万行，基座代码轻量审查）。
> 评估方法：全量阅读 views/services/models/serializers/filters/auth/errors/exception_handlers/seed/settings 与前端 api/composables/utils/views 源码；对照前两轮报告逐项验证"已修复"声明；grep 交叉验证死代码与重复逻辑；对第三方行为（simplejwt `get_user`、DRF `enforce_timezone`、Django ORM None 过滤）读盘核实；逐一核对后端 7 个测试文件（279 例）与前端 17 个 spec（124 例）的函数/分支覆盖。
> 基线状态：后端 `python manage.py test build_protection_service` 279 例全绿；前端 `npm run test` 124 例全绿；工作区无真实未提交改动（仅行尾符噪声）。
> 与前两轮的关系：第一轮（2026-10-11）约 5.5 分、第二轮（2026-10-12）约 7 分，本轮 **前后端均约 7.5 分**。前两轮 P0/P1 主体确已修复并有回归锁定，本轮问题以"修复范式的漏网路径"与"组件层测试盲区"为主，不重复报告已修复项。

## 总体结论

两轮治理后架构骨架健康：错误码/响应契约单一真源、"事务 + 条件 UPDATE 抢占 + partial unique + IntegrityError 转义"的并发范式成体系、前端 BizError/受控开关/退避轮询/展示映射唯一来源等范式在绝大多数页面落地。本轮问题呈三个特征：

1. **已验证范式未推广到残余路径**——非字符串 body 的 500 集群是第二轮 admin 参数守卫的镜像漏网；toggle 是唯一没套"条件 UPDATE"范式的写路径；停用用户存量 token 500 是"停用账号登录 403"修复只覆盖登录口的直接后果。
2. **从未被审视过的系统性契约缺陷**——后端时间序列化存在三种口径并存（手工 strftime 输出 UTC 墙钟、DRF 序列化器输出上海墙钟、DjangoJSONEncoder 输出带 offset 的 UTC），执行轮次/日志/借用流/抢占记录的时间在前端一律早 8 小时展示。
3. **测试策略到达天花板**——纯函数层覆盖扎实，但组件内逻辑（轮询生命周期、弹窗时序、点击分发）零覆盖，本轮前端三个 P1 恰恰全部位于组件层；且第二轮"已勾选完成"项存在漏网分支（说明修复后缺少同类点位全量 grep 复核）。

**P1 = 功能性 bug / 契约破坏（可稳定复现），P2 = 并发 / 审计 / 一致性缺陷，P3 = 细节债务与建议。** 编号规则：B-xx 后端、F-xx 前端；「处置」列标明本轮修复（→ 对应 spec 条目）或记录在案。

---

## 一、后端问题清单（backend/build_protection_service，简写 bps/）

### P1 — 严重

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| B-P1-1 | **停用用户存量 token → 500 而非 401**。simplejwt 5.5.0 `get_user()` 对用户不存在/`is_active=False` 抛 `AuthenticationFailed`（`InvalidToken` 是其子类而非父类），auth.py 只在 `get_validated_token` 处 catch `InvalidToken`，`get_user` 在 try 之外。admin 停用用户后，被停用者 8 小时内存量 token 请求任意端点：函数视图 → 裸 500；ViewSet → contract_exception_handler 归入 APIException → 50000/HTTP 500。前端拿不到 40100 不跳登录。连带 `auth.py:28-29` 的 inactive 判断是死代码 | `bps/auth.py:19-29` | 本轮修复 R3-B1 |
| B-P1-2 | **非字符串请求体字段 → AttributeError → 500**（第二轮 admin 守卫的漏网集群）：① 登录口（未认证面）`{"username":123}` → `(123 or "").strip()` 500、`password` 传数字 → `check_password` 内 `.encode()` 500；② borrow_flow 的 `new_build_time/reason/comment`；③ POST /branches、/projects 的 `name/repository_url/description`；④ reports publish 的 `screenshot` 传对象 → `.encode("utf-8")` 500；⑤ `parse_body` 对合法 JSON 非对象（`[1,2]`/`"str"`/`null`）原样返回，调用方 `body.get(...)` → 500，波及所有普通函数视图 | `bps/views/login.py:40-41`、`borrow_flow.py:115,130,148`、`branch_config.py:111,120-121,372,380-381`、`reports.py:126-129`、`views/__init__.py:96-105` | 本轮修复 R3-B2 |
| B-P1-3 | **时间戳序列化三种口径并存，手工 strftime 输出 UTC 墙钟且无时区标记**：`fmt_dt`（executions 全部时间字段）、borrow_flow `handled_at/created_at`、slot_booking `created_at/released_at`、branch_config `_dt` 直接对 aware UTC datetime `strftime("%Y-%m-%dT%H:%M:%S")`；DRF DateTimeField 经 `enforce_timezone` 输出上海墙钟；admin logs 经 DjangoJSONEncoder 输出 `+00:00`。全后端无一处 `timezone.localtime`。前端 `parseTime` 按本地时间解析无 offset 串 → 执行轮次/日志/借用流/抢占记录**一律早 8 小时展示**，reports 页却正确 | `bps/views/__init__.py:43-45`、`borrow_flow.py:56-59`、`services/slot_booking.py:92,113-114`、`services/branch_config.py:126-127`、`views/admin.py:456,467` | 本轮修复 R3-B3 |

### P2 — 一般

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| B-P2-1 | **toggle 读改写竞态 + 重新启用绕过互斥/阶段校验**：`s.enabled = not s.enabled; s.save()` 全字段保存——并发双 toggle 丢翻转、旧快照覆盖并发 update 的其他字段；且停用 A(22:00) → 他分支建 B(22:00) → 重新启用 A，跨分支资源互斥/同分支阶段冲突**静默生效**无报错（toggle 是唯一未套条件 UPDATE 范式的写路径） | `bps/views/strategies.py:188-195`、`views/admin.py:540-546` | 本轮修复 R3-B4 |
| B-P2-2 | **PM 侧策略 delete/toggle 零审计留痕；delete 级联抹掉执行历史与待审批借用流**：不写 StrategyChangeLog（admin 同款操作有 AdminOpLog，双轨审计）；`ExecutionRound.strategy`/`BorrowFlow.strategy` 均 CASCADE，PM 删策略连带删全部轮次历史与 pending 电子流，无拦截无提示 | `bps/views/strategies.py:174-217`、`models/others.py:99,181` | 本轮修复 R3-B5 |
| B-P2-3 | **update_user 改角色/停用可制造"无主版本"**：不检查该用户是否为某 `Version.pm_user`；把绑定 PM 改成 builder 或停用后，"版本 PM 必须为 pm 角色"不变量被绕过、借用流无人可审批 | `bps/views/admin.py:238-250` | 本轮修复 R3-B6 |
| B-P2-4 | **config PUT 无值域校验**：`int(body[key])` → `true`→1、`45.7`→45 截断、负数照单入库（`build_minutes=-100` 令全部时间线推导失真），与同文件 update_user 严格布尔、模板 minutes 非负校验口径不一致 | `bps/views/admin.py:425-428` | 本轮修复 R3-B7 |
| B-P2-5 | **seed 第二次运行破坏幂等**：`get_or_create(date, template, status="reserved")` 把 status 放进 lookup；首跑末尾释放的 3 条历史记录在第二跑 lookup miss → 重建 reserved，同 (date,template) 出现 released+reserved 双记录。现有幂等测试连跑三次但计数在第二跑后取样、第三跑比对，恰好测不到 1→2 增量 | `bps/management/commands/seed.py:371-383,407-418`、`tests.py:596-608` | 本轮修复 R3-B8 |
| B-P2-6 | **list_strategies 可见性口径不一致**：仅 `role=="pm"` 过滤，builder/tester/integrator 可见全部版本全部策略；与"无绑定 PM fail-closed 空集"及借用流可见性收敛的口径矛盾（plan/weekly 确实全员公开，若"计划公开"是既定设计则 PM fail-closed 反成孤例）——三种语义并存 | `bps/views/strategies.py:81-86` | 本轮定为设计决策并测试锁定 R3-B10 |
| B-P2-7 | **密码策略与令牌吊销缺口**：`AUTH_PASSWORD_VALIDATORS=[]`，建用户/改密只要求非空（`"1"` 可过）；改密码不吊销存量 access token（RevokedToken 仅覆盖 logout），旧 token 改密后仍可用最长 8 小时 | `config/settings.py`、`views/admin.py:199-200,234-237` | 本轮做最小密码长度校验 R3-B13；令牌吊销记录在案 |
| B-P2-8 | **release_booking 非原子**：并发双释放均成功，后者覆盖 released_at/reason；应改条件 UPDATE `filter(status="reserved").update(...)` 对齐既有范式 | `bps/services/slot_booking.py:254-268` | 本轮修复 R3-B9 |

### P3 — 建议（择要，全量见评估底稿）

| 编号 | 问题 | 处置 |
|---|---|---|
| B-P3-1 | 死代码/死分支：`errors.py CODE_OK` 全库零引用（api.py 硬编码 0）、exception_handlers 不可达 Http404 分支、auth.py inactive 死代码、strategies.py 未用 `User` import、login.py 未用 `err` import、weekly.py 无用 `select_related("pm_user")` | 本轮清理 R3-B11 |
| B-P3-2 | 重复代码：toggle IntegrityError 兜底三份、`_create_admin_strategy` 与 `create_strategy` 前奏 ~14 行重复、两套分页实现（`_paginate` vs reports 内联）、`[:200]` 截断 4 处 | 本轮收敛分页与截断 R3-B11；策略创建前奏重复记录在案 |
| B-P3-3 | `security_log` detail 拼接（ua 200 + ip + 业务 detail）可超 max_length=255，SQLite 放行、迁 Postgres 即报错 | 本轮修复 R3-B12 |
| B-P3-4 | 借用审批通过固定 `push_mode="normal"` 且丢弃 `push_start_time`——sync/固定推送策略被借用后推送配置丢失 | 本轮修复 R3-B15 |
| B-P3-5 | 读端点无方法守卫（plan/weekly/executions/logs/me/slot_calendar 任意方法均执行；borrow_flow 列表 DELETE/PUT 当列表返回），与写端点已加守卫的口径不一致 | 本轮修复 R3-B16 |
| B-P3-6 | `update_user {"password": ""}` 静默忽略，与 create"密码必填 42201"口径不一 | 本轮修复 R3-B18 |
| B-P3-7 | RevokedToken `expires_at` 可空且 null 行永不清理（logout 清理只删 `expires_at__lt=now`） | 本轮修复 R3-B11 |
| B-P3-8 | 登录细节：XFF 分支不可达、反代部署后限流联合键退化为纯用户名键、停用账号 403 不写 security_log、不存在用户不走 check_password 恒时路径（计时侧信道枚举） | 记录在案（部署形态相关，改动收益低） |
| B-P3-9 | `_change_desc` 把"显式置 null 清空 push_start_time"与"未提供"混同，清空不进变更日志 | 记录在案 |
| B-P3-10 | plan `_conflicted_ids` O(n²) 每对重算全时间线（n 小，暂无性能问题） | 记录在案 |
| B-P3-11 | settings 生产就绪残留：ALLOWED_HOSTS 默认 `*`、CSRF_TRUSTED_ORIGINS/SECURE_SSL_REDIRECT 未配、JWT_SIGNING_KEY 静默回退 SECRET_KEY、`_IS_TESTING` 启发式脆弱 | 记录在案（部署期处理，模板见 .env.example） |
| B-P3-12 | ReportFilter status/conclusion 垃圾值静默空结果，与 slot 列表 42201 口径不一致 | 记录在案 |
| B-P3-13 | `extra_view` 命名与职责不符（实为版本列表/创建端点） | 记录在案 |

### 后端测试覆盖缺口（函数/分支级，39 项，本轮优先补 ★ 项）

**与 P1/P2 bug 直接对应的零覆盖分支：**
1. ★ auth.py `get_user` 抛 AuthenticationFailed（停用/被删用户存量 token）→ 全端点行为无测试（B-P1-1 存活原因；tests.py:1096 只测登录 403）
2. ★ login_view 非字符串 username/password → 500
3. ★ parse_body 非对象合法 JSON（`[1]`/`null`）
4. ★ POST /branches、/projects 非字符串 name/repository_url/description
5. ★ borrow_flow create/approve/reject 非字符串 new_build_time/reason/comment
6. ★ ReportViewSet.publish 非字符串 screenshot
7. ★ fmt_dt/strftime 各端点时间戳时区口径 → 零断言（无任何测试校验过返回时间值等于本地墙钟）
8. ★ toggle 并发双 toggle 丢翻转、启用后跨分支互斥破坏
9. ★ delete_strategy 级联删除 ExecutionRound/pending BorrowFlow 副作用零断言；PM toggle/delete 无 StrategyChangeLog

**views 层其余缺口：** strategies 不支持方法 → 42201 未测；builder/tester 全量可见未测；update_version 并发重命名 IntegrityError 兜底未测；add_branch 重名 40902 未测；users_view 非 GET/POST 未测；config_view 负数/bool/float 未测；★ executions 列表 PM 隔离未测（round2 只测了详情隔离）；conclusion fail/sync → push_status="" else 分支未测；operator=None → "" 未测；★ reports 分页参数（page/page_size/非法回退/上限 100）整体零测试；update/publish/revisions 404 未测；ReportFilter 纯数字 keyword → pk 匹配未测；BranchProjectViewSet.config StartupConfig 缺失自动创建未测；projects action project_id 不存在 42201 未测；destroy 不存在 pk 40401 未测；_paginate 非法参数回退未测；admin slot list date_from/date_to 非法 42201 未测；SlotTemplateSerializer start>=end 跨天拦截无专测；borrow_flow create strategy_id 不存在 40401 未测；审批时模板已删 → 40401 + set_rollback 分支未测；approve 后再 reject 未测。

**services 层缺口：** `_raise_conflict_or_reraise` 非目标约束 re-raise 未测；update_strategy save 撞约束 40902 未测；并发双释放未测；冲突 holder=None"他人"文案未测；★ build_slot_calendar 12 月边界未测；template_applies_on effective_from/to 等于当天边界未测；mutex check_build_mutex 非法时间 warning 跳过未测；★ timeline sync 模式推送窗口无直接单测；branch_config start_instance IntegrityError → None 未测；advance STOPPED/started_at=None no-op 未测；report_service.update 无变化不留痕未测。

**其他：** ★ seed 第二跑 released→重建 reserved 缺陷未测（测量起点错位）；★ exception_handlers MethodNotAllowed→42201、Throttled→42901、通用 APIException→50000 三个映射未测；logout 过期 token/过期 RevokedToken 清理分支未测。

---

## 二、前端问题清单（frontend/src，业务代码为重点）

### P1 — 严重

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| F-P1-1 | **branch-config 实例轮询"僵尸循环"**：`pollInstances()` 的 `finally { schedulePoll() }` 无"已卸载"守卫；卸载瞬间在途请求 settle 后仍会排上新定时器，此后自我续命——用户离开页面后 `GET /branches/N/instances` 以 5s 间隔（失败退避 60s）无限继续直到关标签页。第二轮轮询治理新代码中的漏洞 | `views/branch-config/index.vue:280-316,341-344` | 本轮修复 R3-F1 |
| F-P1-2 | **StrategyDetailDialog 仍以 `push_start_time` 猜测推送模式**——第二轮 P2-20 同类 bug 的漏网分支（修复只落在 StrategyBorrowDialog）：normal+固定推送时间的策略在只读详情里被误标"同步推送"；该弹窗现被 weekly-new 与 weekly-report 两页复用，影响面扩大；后端载荷与 `WeeklyStrategy` 类型均已含 `push_mode` | `views/weekly-new/components/StrategyDetailDialog.vue:28` | 本轮修复 R3-F2 |
| F-P1-3 | **RecordsPanel 默认日期筛选从未作用于首次加载**：`onMounted` 先 `load()`（dateRange 为 null → 全表查询）后才赋"近一个月"默认值且不再 load——筛选器显示着日期范围，表格展示的却是未过滤的全部记录 | `views/slot-config/components/RecordsPanel.vue:256-270` | 本轮修复 R3-F3 |

### P2 — 一般

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| F-P2-4 | **动作类 async 处理器 try/finally 无 catch 成片残留**（第二轮只修了加载函数）：BizError 从模板事件处理器逃逸为 Uncaught rejection。branch-config 6 个保存/启停函数 + 2 个删除调用裸奔；StrategiesTab.saveAdminStrategy 裸 await 且无 :loading 防双击；VersionsTab.saveVersion/addBranch 同款；ConfigTab.loadConfig/saveConfig（onMounted 失败即未处理）；StrategyEditDialog.onSave、StrategyBorrowDialog.onSubmit、report/detail.saveDraft 均 finally 无 catch | 见评估底稿逐文件行号 | 本轮修复 R3-F5 |
| F-P2-5 | **展示映射"唯一来源 constants.ts"三类漏网**：① push_mode 文案三种变体散布 6 文件 8 处；② 抢占状态映射在 RecordsPanel 与 MyBookingsDrawer 逐字复制两份（各含不可达"已过期"死分支）；③ 星期中文数组 6 份（三份"周日"开头、两份"周一"开头、一份对象版） | 见评估底稿 | 本轮修复 R3-F4 |
| F-P2-6 | **StrategyEditDialog 仍绕过 API 层裸调 `http.get("/admin/templates")`**——第二轮 F-P2-12 声称修复两处实际只改了一处，且该弹窗被 weekly-report 复用，坏范式扩散到第三个入口 | `views/weekly-new/components/StrategyEditDialog.vue:121,163-165` | 本轮修复 R3-F6 |
| F-P2-7 | **`WEEKDAY_CN` 死代码且注释与后端契约相反**：注释称后端返回英文星期，实际 weekly.py 已返回中文；映射永不命中、恒走 `?? d.weekday` 兜底——功能侥幸正确，文档误导后人，spec 夹具用中文导致该分支从未被测到 | `composables/useWeeklyPanorama.ts:47-56,136-141` | 本轮修复 R3-F7 |
| F-P2-8 | **`timeRows` 对每个时间点重复调用 `tasksAtTime` 7 次**（第二轮 P2-18 点名未修）：每行 7 个 cell 各自重建内容相同的任务数组，O(时间点×7×策略数) 重复构建，两个周页共用放大影响 | `composables/useWeeklyPanorama.ts:208-223` | 本轮修复 R3-F7 |
| F-P2-9 | **report/detail.vue 遗留三件套**：`setTimeout(resolve, 100)` 魔法等待仍在；`loadHistory` 无分页拉全量报告只为下拉框（后端已支持分页，`ReportQuery` 未跟进）；`base64Bytes/dataUrlToBlob` 未抽取未测试（round2 阶段六唯一未勾选项） | `views/report/detail.vue:278,358-364` | 本轮修复 R3-F8 |
| F-P2-10 | **`getMe` 定义后全库零调用 + 身份快照永不刷新**：`build-user-info` 是登录时刻 localStorage 快照，服务端改角色/换绑定版本后前端到下次重新登录前无感知（canEditPanorama、审批权限、admin 判定全部基于旧快照） | `api/auth.ts:21` | 本轮接线：应用启动 silent 刷新 R3-F10 |
| F-P2-11 | **类型闸与 any 残留**：strict:false、no-explicit-any:off；业务 `catch (e: any)`×4；`VersionItem.status: string` 非字面量联合（VersionsTab `"active" as string` 连带放弃联合）；store `loginByUsername(data)` 隐式 any | 多处 | 本轮修 catch 与 status 联合 R3-F9；strict 记录在案 |

### P3 — 建议（择要）

| 编号 | 问题 | 处置 |
|---|---|---|
| F-P3-1 | branch-config `new Date().toISOString().slice(0,10)` 取 UTC 日期，东八区 0:00-8:00 拿昨天查 /plan；全库其余 10+ 处均用 dayjs 本地 | 本轮修复 R3-F11 |
| F-P3-2 | 死代码/死导出：branch-config 导入 `deleteBranch` 未用；`getProjects/createProject` 无消费者；`polling.shouldNotify` 无生产调用者仅测试引用（"为死代码维护测试"）；weekly 两页解构的 `strategies` 未用；weekly-new `onMonthWeekChange` 空值兜底死逻辑；基座刷新链（handRefreshToken → /refresh-token）不可达但整套仍在 | 本轮清理业务侧 R3-F11；基座刷新链记录在案 |
| F-P3-3 | borrow-flow 手写 `.replace("T", " ")` 时间格式化 5 处，未走 `utils/business.formatTime` | 本轮统一（验证输出等价）R3-F11 |
| F-P3-4 | magic number：slot-booking horizon `?? 60` 两份、页大小 20 内联多处 | 本轮提常量 R3-F11 |
| F-P3-5 | MyBookingsDrawer.loadMore 无在途守卫，连点并发请求同页重复 append | 本轮修复 R3-F11 |
| F-P3-6 | StartupConfigForm `addEnv` 写入空键 `env_vars[""]` 直接提交后端；renameEnv 因 delete+add 使被编辑行跳到列表末尾 | 本轮修复空键守卫 R3-F11 |
| F-P3-7 | ReportHeader pips 整周已过去（elapsed=7）时第 7 格仍标"today"呼吸圈 | 本轮修复 R3-F11 |
| F-P3-8 | welcome 页文案仍写"深色科技风周报看板"，weekly-report 已浅色化（c83882c） | 本轮修复 R3-F11 |
| F-P3-9 | useWeeklyPanorama `today` setup 一次性求值，跨零点长驻后今天高亮/过期判定漂移；HourTrendPanel"现在"参考线同款 | 记录在案（低频场景） |
| F-P3-10 | HourGrid 与 TechHourGrid 近克隆（weekdayIndex/isWeekend/DayCell 三份实现） | 记录在案（视觉刻意分叉） |
| F-P3-11 | week 下拉越月失效（翻周到上/下月后 selectedWeek 不在 options 中，显示裸日期串） | 记录在案 |
| F-P3-12 | `borrowFlowUrl` 未复用 `appHashUrl`，api 层保留展示性 URL 构造职责 | 本轮顺手统一 R3-F11 |
| F-P3-13 | getPlan 被 6 个页面当"版本/分支字典"反复调用（聚合端点带全量时间线+冲突计算，作下拉选项来源偏重） | 记录在案（架构级，需后端新端点） |
| F-P3-14 | logs 页 loadOps/loadSecurity 无 loading 态；field/event/action 展示英文原值无映射 | 记录在案 |
| F-P3-15 | 非 scoped 全局样式（weekly-report `@use "./theme.scss"`，wk- 前缀命中风险低）；report/detail 两处 console.error（带前缀有意为之） | 记录在案 |

**安全面**：业务代码无 v-html/dangerouslyUseHTMLString；token 走基座 cookie+localStorage 双存储（模板既有设计）；SlotChip 对他人姓名已脱敏；未发现新增安全问题。

### 前端测试覆盖缺口（函数/分支级）

**纯函数已存在但分支缺失：**
1. ★ `views/borrow-flow/format.ts formatBorrowFlowText`：approved 分支（"通过"文案）无测试（现有仅测 rejected）；`approver_name=null` 的 "-" 兜底、`handle_comment` 为空不拼括号、`handled_at=null` 三个兜底分支无测试
2. ★ `utils/weeklyReport.ts computeHourTrend`：非法/越界时间（"25:00"、非数字）**当前实现会直接 TypeError**——缺测试掩盖了未设防边界（需先加守卫再补测）；computeTagCloud 字号封顶 22px 与三键排序无断言；computeKpis today 不在展示周的语义无测试
3. `utils/business.ts parseTime`：带 "Z" 的 ISO 串、完全非法输入回退分支无测试；formatTime 非法输入无测试
4. ★ `useWeeklyPanorama`：序号守卫（weeklySeq）丢弃过期响应分支无测试（快速翻周/切版本乱序返回是历史高发缺陷区）；resolveTaskClick 失败 → null 分支无测试；strategyDetailList 缓存语义（二次点击不重复请求、invalidate 后重拉）无测试
5. ★ `api/http.ts`：40101 分支无测试（仅测 40100）；`silent: true` + 401 组合（静默请求也必须跳登录）无测试
6. `store/modules/user.ts tokenExpiresAt`：JWT exp 解析成功/非法回退 8h——安全相关纯函数因模块私有而零测试（建议导出后补测）

**可测但未抽取（组件内嵌纯逻辑，零覆盖）：**
7. ★ `report/detail.vue base64Bytes/dataUrlToBlob`（round2 阶段六唯一未完成项）——本轮抽取到 utils 并补测
8. HourGrid/TechHourGrid 的 weekdayIndex/isWeekend/shortDate、DayCell 的 isPast/visibleEntries（MAX_VISIBLE=5 截断）与 chipAria、SlotChip 的 variant 三态与 ownerLabel 脱敏
9. slot-booking onChipClick 四路分发与 setMonth-watcher 协同（第二轮 P1-4 修复点无回归锁定）
10. branch-config 轮询生命周期：失败退避、hidden 暂停、切分支作废在途、卸载终止（F-P1-1 所在，有测试早就拦住了）
11. RecordsPanel 初始筛选时序（F-P1-3 所在）；ReportHeader elapsed 0/7 边界

**结构性盲区**：全库没有任何 .vue 组件挂载测试——上述 8-11 类"组件内纯逻辑"当前测试策略覆盖不到。**处置**：本轮建立最小可行路径——能抽取为纯函数的一律抽取后补测（7、10 的调度逻辑、11 的时序逻辑）；完整组件测试基建（@vue/test-utils + 挂载环境）记录在案作为第四轮候选。

**反向缺口**：`polling.shouldNotify` 有 2 例测试但生产零调用——随死代码一并删除。

---

## 三、评分与轨迹

| 轮次 | 后端 | 前端 | 说明 |
|---|---|---|---|
| 第一轮 2026-10-11 | ~5.5 | ~5.0 | 契约混乱、并发缺陷、生产阻断项成片 |
| 第二轮 2026-10-12 | ~7.0 | ~6.5 | 范式建立，主路径修复扎实 |
| **第三轮 2026-10-13** | **~7.5** | **~7.5** | 范式漏网路径 + 时区契约缺陷 + 组件层测试盲区 |

**简评**：本轮问题不再是"没有范式"，而是"范式没有推广完"。后端三个 P1 全部是已验证做法（类型守卫、条件 UPDATE、统一契约）在残余路径的镜像缺失，外加一个从未被审视的时间序列化契约缺陷；前端三个 P1 全部位于组件层——恰是测试策略的盲区。第三轮优化（spec：`docs/superpowers/specs/2026-10-13-code-quality-optimization-round3-design.md`）以三条主线推进：**① 把已验证范式推广到全部残余路径；② 时间契约单点收敛；③ 可抽取逻辑纯函数化 + 测试锁定**，并对第二轮所有"已勾选完成"项做全库交叉复核。
