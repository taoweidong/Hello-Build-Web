# 第三轮代码质量优化设计（2026-10-13）

> 依据：`docs/code-quality-assessment-2026-10-13.md`（第三轮全库复评）。
> 主线：**① 把已验证范式推广到全部残余路径；② 时间契约单点收敛；③ 可抽取逻辑纯函数化 + 测试锁定。**
> 纪律：每阶段完成后必须全量测试通过（后端 `python manage.py test build_protection_service`，前端 `npm run test` + `npm run typecheck`）才进入下一阶段；行为有变化的条目同步更新对应 spec 与 AGENTS.md。
> 编号规则：R3-Bxx 后端、R3-Fxx 前端，对应评估报告中的问题编号。

## 阶段一：后端 P1（正确性 / 契约破坏）

### R3-B1 停用用户存量 token → 40100（修 B-P1-1）
- `bps/auth.py`：将 `self.get_user(validated)` 纳入 try，catch `(InvalidToken, AuthenticationFailed)`（`rest_framework.exceptions.AuthenticationFailed`）后 `return None`；删除 `user is None or not user.is_active` 死代码（保留 `user is None` 防御可，但注释说明 get_user 不返回 inactive）。
- 效果：停用/被删用户的存量 token 走既有"未认证"路径 → 40100，前端跳登录。
- 测试（tests_quality_round3.py，下同）：admin 停用用户后，用其存量 access token 请求函数视图（如 /strategies）与 ViewSet（如 /reports）均返回 40100 而非 500。

### R3-B2 非字符串 body 字段类型守卫（修 B-P1-2）
- `bps/views/__init__.py parse_body`：JSON 合法但非 dict → 返回 `{}`（与非法 JSON → 42201 区分开）。
- 新增共享助手 `body_str(body, key, *, default="", max_len=None)`：值非 str → 返回 default 或抛参数错误（口径：取 `""` 走既有"必填/非法"分支，避免新错误码）；`max_len` 超长截断或拒绝按调用点既有语义。
- 应用点：`views/login.py`（username/password 非 str → 42201"参数非法"，不得 500）、`views/borrow_flow.py`（new_build_time/reason/comment）、`views/branch_config.py`（POST branches/projects 的 name/repository_url/description）、`views/reports.py`（publish screenshot 非 str → 42201）。
- 测试：上述每个入口传数字/数组/对象/null → 42201 或既有校验错误码，绝无 500；parse_body 传 `[1,2]`、`"str"`、`null` → 各视图按缺参处理。

### R3-B3 时间序列化单点收敛到上海墙钟（修 B-P1-3）
- 约定（写入 AGENTS.md）：**所有对外时间戳统一为 Asia/Shanghai 本地墙钟、格式 `"%Y-%m-%dT%H:%M:%S"`、不带 offset**（与 DRF DateTimeField 现行为一致，前端 parseTime 按本地解析即正确）。
- `bps/views/__init__.py fmt_dt`：先 `timezone.localtime(dt)` 再 strftime；None 返回 `""` 不变。
- 同款修正：`views/borrow_flow.py:56-59`、`services/slot_booking.py:92,113-114`、`services/branch_config.py _dt`。
- `views/admin.py` logs 两处 datetime 直塞 JsonResponse → 改用 `fmt_dt`。
- 测试：freeze 一个已知 UTC 时刻（如 `2026-10-13T02:00:00Z`），断言 executions/borrow_flow/slot records/admin logs 返回 `2026-10-13T10:00:00`（上海墙钟）。

## 阶段二：后端 P2（并发 / 审计 / 一致性）

### R3-B4 toggle 条件 UPDATE + 启用方向跑校验（修 B-P2-1）
- `views/strategies.py toggle_strategy` 与 `views/admin.py` 同款：改为事务内条件 UPDATE `Strategy.objects.filter(id=sid, enabled=旧值).update(enabled=新值)`，rowcount=0 → 40902（并发已被改）；**启用方向**（false→true）先调用 `services.strategies` 既有校验（validate_strategy 或复用 update 路径校验）冲突 → 40901/40902。
- 保留 IntegrityError → 40902 兜底。
- 测试：并发双 toggle 仅一次生效（第二次 40902 或幂等语义明确）；停用 A → 他分支建同刻 B → 重新启用 A → 40901（跨分支互斥拦截）。

### R3-B5 PM toggle/delete 审计 + delete 拦截 pending 借用流（修 B-P2-2）
- `views/strategies.py`：toggle/delete 写 StrategyChangeLog（action 用既有枚举 toggle/delete，operator=当前用户）；delete 前检查 `BorrowFlow.objects.filter(strategy=s, status="pending").exists()` → 40903"存在待审批借用流，请先处理"。
- 测试：toggle/delete 后 StrategyChangeLog 有记录；有 pending 借用流时 delete → 40903；无 pending 时删除成功。

### R3-B6 update_user 角色/停用守卫绑定版本（修 B-P2-3）
- `views/admin.py update_user`：变更 role（离开 pm）或 is_active→False 前检查 `Version.objects.filter(pm_user=user).exists()` → 40902"该用户仍绑定版本 PM，请先移交"。
- 测试：绑定 PM 改 builder / 停用 → 40902；移交后成功。

### R3-B7 config PUT 值域校验（修 B-P2-4）
- `views/admin.py config_view`：改用 `parsing.parse_int`（拒 bool/float 串），且要求 `>= 0`（build_minutes 等允许 0？口径：非负；如既有语义要求正数则 ≥1，以现网默认值为准），非法 → 42201。
- 测试：`true`/`45.7`/`-1`/`"abc"` → 42201；合法整数写入成功。

### R3-B8 seed 幂等修复（修 B-P2-5）
- `seed.py _seed_slot_bookings`：`get_or_create` lookup 去掉 status（以 date+template 为锚）；defaults 里带 status="reserved"。
- 测试修正：连跑两次后**立即**断言 SlotBooking 总数不变（含 released 行不被复活），第三跑再断言一次。

### R3-B9 release_booking 条件 UPDATE（修 B-P2-8）
- `services/slot_booking.py release_booking`：改 `filter(id=..., status="reserved").update(status="released", released_at=..., reason=...)`，rowcount=0 → 按既有"已释放"语义返回（幂等或报错，保持现有对外行为，读现码定）。
- 测试：并发/重复释放仅第一次生效，released_at/reason 不被覆盖。

### R3-B10 list_strategies 可见性定为设计决策并锁定（修 B-P2-6）
- 决策：**策略计划对全员可见**（plan/weekly 本就公开），PM 的过滤语义是"默认只看自己版本"而非安全边界；无绑定版本的 PM 取空集（fail-closed）维持不变（防止 PM 误操作他版策略）。
- 落地：`views/strategies.py list_strategies` 补注释说明口径；不改行为。
- 测试：builder/tester/integrator 可见全量；无绑定 PM 空集；有绑定 PM 只见自己版本。

## 阶段三：后端 P3 清理 + 测试补全

### R3-B11 死代码与重复清理（修 B-P3-1/2/7）
- 删除：`errors.py CODE_OK` 零引用常量或让 `api.py ok()` 引用它（二选一，倾向 api.py 引用常量）；`exception_handlers.py` 不可达 Http404 else 分支；`views/strategies.py` 未用 `User` import；`views/login.py` 未用 `err` import；`views/weekly.py` 无用 `select_related("pm_user")`。
- `views/login.py logout` 清理 RevokedToken 时同时删 `expires_at__isnull=True` 行。
- 分页收敛：reports 内联分页改用 `views/slot_booking._paginate`（提升为 `views/__init__.py` 共享助手 `paginate_qs`），页大小常量集中定义。
- 测试：既有测试全绿即回归锁定；logout 清理行为补 1 例（过期/null 行被删）。

### R3-B12 security_log detail 截断（修 B-P3-3）
- `views/__init__.py security_log`：拼接后 `detail[:255]`。
- 测试：超长 ua + detail 入库不超 255。

### R3-B13 最小密码校验（修 B-P2-7 部分）
- `views/admin.py` create_user/update_user：密码长度 < 6 → 42201"密码至少 6 位"（seed 的 123456 合规；不动 AUTH_PASSWORD_VALIDATORS，避免影响 Django 内部表单）。
- 测试：`"1"` → 42201；6 位以上成功。

### R3-B15 借用审批保留推送配置（修 B-P3-4）
- `views/borrow_flow.py` 审批通过创建新策略时：`push_mode`/`push_start_time` 从源策略复制，不再固定 normal。
- 测试：sync 策略借用通过后新策略 push_mode=sync、push_start_time 保留。

### R3-B16 读端点方法守卫（修 B-P3-5）
- plan/weekly/executions/logs/me/slot_calendar/borrow_flow 列表等读端点：`request.method != "GET"` → 42201（统一走 fail_resp）。
- 测试：DELETE /borrow-flows、PUT /plan → 42201，无副作用。

### R3-B18 update_user 空密码串口径统一（修 B-P3-6）
- `{"password": ""}` → 42201（与 create 一致）；不提供 password 键 → 不改密码（保持）。
- 测试：空串 → 42201；缺键 → 密码不变。

### R3-B14 测试缺口补全（后端）
新增/补齐以下测试（优先级 ★ 为评估报告标注）：
- ★ executions **列表** PM 隔离（他版数据不可见）
- ★ reports 分页：page/page_size 生效、非法 page 回退、page_size 上限 100、不带 page 返回全量数组（向后兼容）
- ★ exception_handlers 映射：MethodNotAllowed → 42201、Throttled → 42901、通用 APIException → 50000
- ★ build_slot_calendar 12 月边界（跨年周矩阵）
- ★ timeline sync 模式推送窗口（build_start − push − buffer）
- conclusion fail/sync → push_status="" else 分支；operator=None → ""
- borrow_flow：create strategy_id 不存在 40401；审批时模板已删 → 40401 + 回滚；approve 后再 reject → 既有终态语义
- template_applies_on effective_from/to 等于当天边界
- _paginate 非法 page/page_size 回退；admin slot list date_from/date_to 非法 42201
- add_branch 重名 40902；update_version 并发重命名 IntegrityError 兜底
- ReportFilter 纯数字 keyword → pk 匹配
- services：update_strategy save 撞约束 40902；mutex 非法时间 warning 跳过；report_service.update 无变化不留痕
- strategies 不支持方法（PUT /strategies、POST /strategies/<id>）→ 42201

**记录在案不实施**（理由见评估报告）：B-P3-8 登录侧信道/XFF、B-P3-9 change_desc null 语义、B-P3-10 plan O(n²)、B-P3-11 settings 生产加固（部署期）、B-P3-12 ReportFilter 值域、B-P3-13 extra_view 改名、改密吊销存量 token（需启用 simplejwt CHECK_REVOKE_TOKEN，影响面大，第四轮候选）。

## 阶段四：前端 P1

### R3-F1 branch-config 僵尸轮询（修 F-P1-1）
- 增加 `let disposed = false`；`onBeforeUnmount` 置 true；`schedulePoll()` 首行 `if (disposed) return;`。
- 测试：轮询调度逻辑若可抽取则抽为纯函数补测；否则以代码审查 + 既有 polling 工具测试兜底（在 plan 中注明）。

### R3-F2 StrategyDetailDialog 推送模式判定（修 F-P1-2）
- 改判 `strategy?.push_mode === "sync"`，文案走 constants 新增的 `pushModeMeta`（见 R3-F4）。

### R3-F3 RecordsPanel 初始筛选时序（修 F-P1-3）
- `dateRange` 默认值（近一个月）赋值移到 `onMounted` 的 `load()` 之前，确保首查即带筛选。

## 阶段五：前端 P2

### R3-F4 展示映射收敛（修 F-P2-5）
- `views/constants.ts` 新增：`pushModeMeta`（normal/sync → 短文案 + 长文案两套 label，覆盖现有 8 处的两种措辞：如 `label`（"正常流程/同步推送"）与 `fullLabel`（"正常流程推送/同步推送冒烟"））；`bookingStatusMeta`（reserved/released，删除不可达 expired 分支）。
- `utils/week.ts` 新增导出：`WEEKDAY_CN_MON`（周一…周日）、`WEEKDAY_CN_SUN`（周日…周六）两个常量数组，替换 6 份手写数组（TemplateDialog 对象版改由数组派生）。
- 替换点：strategy/index.vue×2、StrategiesTab、StrategyEditDialog、StrategyBorrowDialog、StrategyDetailDialog（push_mode）；RecordsPanel、MyBookingsDrawer（状态映射）；BookingDialog、MyBookingsDrawer、SlotDetailDialog、MonthGrid、slot-config/index、TemplateDialog（星期数组）。
- 测试：constants.spec.ts 补 pushModeMeta/bookingStatusMeta 断言；week.spec.ts 补两个数组长度/首尾断言。

### R3-F5 动作路径错误处理统一（修 F-P2-4）
- 逐文件补 `catch`（拦截器已弹 toast，catch 内 `return`/复位状态即可）：branch-config 的 createBranch/addProject/removeProject/saveConfig/startInstance/stopInstance/savePermission/removePermission；StrategiesTab.saveAdminStrategy；VersionsTab.saveVersion/addBranch；ConfigTab.loadConfig/saveConfig；StrategyEditDialog.onSave；StrategyBorrowDialog.onSubmit；report/detail.saveDraft。
- 保存类按钮补 `:loading`（StrategiesTab、VersionsTab、StrategyEditDialog、StrategyBorrowDialog、branch-config 各对话框保存钮），防重复提交。
- 口径写入 AGENTS.md：动作类 async 处理器必须 try/catch/finally 完整，禁止裸 await。

### R3-F6 StrategyEditDialog 走 API 层（修 F-P2-6）
- `http.get("/admin/templates")` → `adminApi.getTemplates()`。

### R3-F7 useWeeklyPanorama 清理（修 F-P2-7/8）
- 删除 `WEEKDAY_CN` 死映射与错误注释，直接用后端中文 weekday（保留 `?? ""` 兜底）；更新对应 spec 夹具注释。
- `timeRows`：每个时间点只调一次 `tasksAtTime(t)`，7 个 cell 复用同一数组（注意 cell 内如需按日期过滤则保留过滤、只共享构建结果——以现码语义为准，不得改变渲染输出）。
- 测试：既有 useWeeklyPanorama.spec 全绿；补 timeRows 行数/内容断言（若现测试未覆盖）。

### R3-F8 report/detail.vue 三件套（修 F-P2-9）
- `setTimeout(resolve, 100)` → 双 `nextTick`（或 requestAnimationFrame）。
- `api/report.ts ReportQuery` 增加 `page/page_size`；`loadHistory` 改分页拉取（page_size=100 一页足够下拉框用，带 total 不再全量循环）。
- 抽取 `base64Bytes`/`dataUrlToBlob` 到 `utils/screenshot.ts`（纯函数，含无逗号 dataURL、空 body、mime 兜底 image/png 边界）+ 新增 `utils/__tests__/screenshot.spec.ts`。

### R3-F9 类型收敛（修 F-P2-11 部分）
- 4 处 `catch (e: any)` → `catch (e)` + `api/http.ts` 导出的 `isBizError(e)` 类型守卫（或 `(e as BizError).code`），消除 any。
- `api/types.ts VersionItem.status` → `"active" | "archived"`（读后端确认值域后定）；VersionsTab 去掉 `"active" as string`。
- `store/modules/user.ts loginByUsername(data)` 补参数类型。

### R3-F10 getMe 接线刷新身份快照（修 F-P2-10）
- 应用启动（`src/api/index.ts` 或 App.vue onMounted，选对基座侵入最小处）：已登录时 `getMe({ silent: true })` 成功则更新 `build-user-info` localStorage 快照与 user store；失败静默忽略（401 由既有拦截器处理）。
- 测试：api 契约测试补 getMe 端点断言（若 moduleContract.spec 模式适用）。

## 阶段六：前端 P3 清理 + 测试补全

### R3-F11 P3 清理（修 F-P3-1/2/3/4/5/6/7/8/12）
- branch-config `toISOString().slice(0,10)` → `dayjs().format("YYYY-MM-DD")`。
- 删死代码：branch-config 未用 `deleteBranch` import；weekly 两页未用 `strategies` 解构；weekly-new `onMonthWeekChange` 死兜底；`api/branchConfig.ts getProjects/createProject`（确认全库无消费者后删）；`utils/polling.ts shouldNotify` + 对应 2 例测试。
- borrow-flow/format.ts 与 index.vue 的 5 处 `.replace("T", " ")` → `utils/business.formatTime`（先验证输出逐字节等价，等价才替换；不等价则保持并记录）。
- slot-booking horizon `?? 60` 提为模块常量 `DEFAULT_HORIZON_DAYS`；页大小 20 提常量。
- MyBookingsDrawer.loadMore 加在途守卫（loading 中直接 return）。
- StartupConfigForm.addEnv：已有空键行时不再新增（聚焦既有空键行）；保存前过滤空键。
- ReportHeader pips：`elapsed >= 7` 时不标 today。
- welcome 页文案去掉"深色科技风"。
- `api/borrowFlow.ts borrowFlowUrl` 改用 `utils/appUrl appHashUrl`。

### R3-F12 测试缺口补全（前端）
- ★ formatBorrowFlowText：approved 分支、approver_name=null、handle_comment 空、handled_at=null
- ★ computeHourTrend：非法时间（"25:00"、非数字、空串）**先加守卫**（跳过非法条目，不得 TypeError）再补测；computeTagCloud 字号封顶与三键排序；computeKpis today 不在展示周
- ★ api/http：40101 跳登录；silent + 401 组合仍跳登录但不弹 toast
- ★ useWeeklyPanorama：weeklySeq 过期响应丢弃；resolveTaskClick 失败 → null；strategyDetailList 缓存与 invalidate
- parseTime 带 Z 串/非法输入；formatTime 非法输入
- tokenExpiresAt：从 store 导出（或抽 utils）后补测 exp 解析成功/非法回退 8h
- utils/screenshot.spec.ts（随 R3-F8 新增）
- constants/week 新增映射断言（随 R3-F4）

**记录在案不实施**：tsconfig strict 与 no-explicit-any 开启（渐进债务）、完整 .vue 组件挂载测试基建（第四轮候选）、HourGrid/TechHourGrid 合并、week 下拉越月、getPlan 字典端点、logs 页 loading 态与英文值映射、跨零点 today 快照、基座 handRefreshToken 死链清理（模板代码）、weekly-report 非 scoped 样式。

## 验收标准

1. 后端全量测试通过，用例数 ≥ 279 + 本轮新增（预期 ≥ 330）；前端 vitest 全过（预期 ≥ 150）、`npm run typecheck` 通过、`npm run build` 通过。
2. 评估报告中所有标记"本轮修复"的条目落地并有对应测试锁定；"记录在案"条目在本文档留痕。
3. AGENTS.md 更新：测试基线数字、时间序列化口径（R3-B3 约定）、动作路径 catch 口径（R3-F5）、第三轮文档索引、策略可见性设计决策（R3-B10）。
4. 对第二轮 spec 所有已勾选完成项做一次全库 grep 交叉复核（防止再出 F-P2-6 式漏网），结果记入 plan 文档。

## 实施记录（2026-10-13 完成）

- 后端测试 279 → **371 例全绿**（新增回归集中在 `tests_quality_round3.py`，超过验收预期 ≥330）；前端测试 124 → **156 例全绿**（超过验收预期 ≥150）；`npm run typecheck`、`npm run build` 通过。本轮无模型改动，无新迁移。
- **偏差记录**（与设计的差异，均有理由）：
  1. R3-B5 删除策略的审计落点：设计写"toggle/delete 写 StrategyChangeLog"，实施中 **delete 的审计改落 `AdminOpLog`**——`StrategyChangeLog.strategy` 为 CASCADE，随策略删除会被级联抹掉，删除类审计必须落独立存续的表（action 沿用 `delete_strategy`，管理端"操作日志"可溯源）；toggle 仍写 StrategyChangeLog。
  2. R3-B9 释放幂等语义：设计留"幂等或报错，读现码定"，实施取 **rowcount=0 → 42201「该记录不是待占用状态，无法释放」**——与入口既有 status 检查的对外报错语义一致，不引入静默幂等。
  3. R3-B13 最小密码长度取 **6 位**（seed 演示账号 123456 合规）；不动 `AUTH_PASSWORD_VALIDATORS`，改密吊销存量 token 维持"记录在案"。
  4. R3-F1 轮询调度逻辑未抽纯函数：以 `disposed` 卸载守卫 + `schedulePoll` 首行短路落地（代码内注释说明），回归依赖既有 polling 工具测试与代码审查。
  5. R3-F8 截图等待采用 **双 `nextTick`**（第一次冲刷响应式状态、第二次确认 DOM 更新完成）。
  6. R3-F10 `getMe` 接线点选 **`App.vue` mounted**（`utils/identity.ts refreshBusinessUser()`，对基座侵入最小；已登录才拉取，失败静默）。
  7. R3-F9 `VersionItem.status` 联合定为 `"active" | "archived"`（与后端 `views/admin.py _VALID_STATUSES` 核对一致）。
- 新增共享层：后端 `views/__init__.body_str`（非字符串字段归一）、`paginate_qs`（分页唯一实现，slot 记录与 reports 共用）、`services/strategies.toggle_strategy`（启停唯一写路径）、服务层 `slot_booking._fmt_dt`/`branch_config._dt` 上海墙钟同款；前端 `utils/identity.ts`、`utils/token.ts`、`utils/screenshot.ts`、`views/borrow-flow/format.ts formatFlowTime`、`views/constants.ts pushModeMeta/bookingStatusMeta`、`utils/week.ts WEEKDAY_CN_MON/WEEKDAY_CN_SUN`。
- AGENTS.md / README / 四份 feature spec 已同步（详见 plan 文档「全量回归与文档同步」节）；第二轮已勾选项全库 grep 交叉复核结论见 plan 文档「交叉复核记录」节。
