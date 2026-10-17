# 第五轮代码质量优化设计（2026-10-18）

> 对应评估报告：`docs/code-quality-assessment-2026-10-18.md`。本轮修复 R5-B1~B13（后端全部）、R5-F1~F12/F14~F17（前端，F13 记录在案）、R5-T1（测试基建）。后端回归测试集中在 `tests_quality_round5.py`；前端回归并入既有 spec 与新增 spec。

## 设计原则

1. **对齐既有范式而非发明新范式**：seq 守卫、条件 UPDATE、savepoint+IntegrityError、body_str/check_str_len、:loading 在途守卫、展示映射唯一来源——全部按前四轮已验证实现推广。
2. **「校验过度」修复以领域设计契约为准绳**：停用策略不占时段（唯一约束只限 enabled）、报告域是文本快照（不建外键）——校验时机与范围对齐契约，而非放松校验。
3. **拒绝优于静默转换**：非 str 载荷一律 42201，不做 repr 化/截断入库（延续 R4-B10 取向）。
4. 每项修复必须有回归测试锁定；行为变化同步更新 AGENTS.md 与相关文档。

## 一、后端修复设计

### R5-B1 update_strategy 仅启用态跑冲突校验（P1）

`services/strategies.py update_strategy`：把无条件的 `validate_strategy(...)` 改为 `if enabled: validate_strategy(...)`（enabled 为 body 与库存值合成后的**结果态**）。语义对齐 `toggle_strategy`（仅启用方向重跑校验）：

- 停用策略改名/改时间/改推送：放行（不占时段，无互斥实害）；
- `PATCH {"enabled": false}` 对冲突漂移策略：放行（恢复「先停用归档」逃生通道，与 toggle 一致）；
- 结果态为启用：完整校验不变（name/push_mode/时间格式/互斥/阶段）。

注意：`validate_strategy` 内还包含 name/push_mode/build_start_time 的**格式校验**，这些对停用策略仍应生效——因此不是整体跳过，而是拆出「格式校验恒跑、冲突校验仅启用态跑」。实现：`validate_strategy` 增加 `check_conflicts: bool = True` 参数，update_strategy 传 `check_conflicts=enabled`；toggle 启用方向不变。PM（`views/strategies.py`）与 admin（`views/admin.py`）两入口共用服务层，一处修复两处生效。

### R5-B2 _raise_conflict_or_reraise 双格式匹配（P2）

`services/strategies.py`：匹配条件补约束名——`"uniq_active_strategy_branch_time" in msg or ("strategy.branch_id" in msg and "build_start_time" in msg)`，与 `slot_booking._raise_conflict_or_reraise`（R4-B8）完全对齐；非目标约束仍 re-raise。

### R5-B3 报告域 username 快照字段扩到 150（P2）

`models/report.py`：`Report.created_by_username`、`ReportRevisionLog.operator_username` max_length 100→150（与 `User.username` AbstractUser 上限对齐，快照语义无损）。出 migration（`makemigrations build_protection_service`，仓库惯例必须提交迁移文件）。

### R5-B4 报告配对校验仅在快照字段变化时执行（P1）

`serializers/report.py ReportSerializer.validate`：存在性/配对校验（「版本与策略须同时选择」+「策略属于所选版本」）仅当 ① 创建（instance is None），或 ② update 且 `version_name`/`strategy_name` 相对库存值发生变化时执行；快照字段未动则跳过活校验，remark/summary/conclusion 等字段的自身校验不变。publish 路径本来就不重跑，口径由此统一为「快照落库后不再活校验」。

### R5-B5 ReportService.update 精准字段保存（P2）

`services/report_service.py update`：收集实际变更字段，`report.save(update_fields=[...变更字段..., "updated_at"])`——不再全字段覆盖，status/publish_count/published_at 不被陈旧内存值回滚。结论锁检查保留（低概率窗口内的锁绕过属可接受残余风险，update_fields 已消除数据回滚实害；如需彻底可后续改条件 UPDATE，本轮记录）。

### R5-B6 logs_view GET-only 守卫（P3）

`views/admin.py logs_view` 开头补 `if request.method != "GET": return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")`；`tests_quality_round3.py` guard 矩阵补该端点两行（POST/DELETE）。

### R5-B7 branch_config 两处 check-then-create 兜底（P3）

`views/branch_config.py`：permissions 的 `update_or_create` 与 projects 的 `exists()`+`create` 均包 `transaction.atomic()` + `except IntegrityError` → 40903（「重复关联/授权」语义，错误码沿用既有 40903 定义），与 R4-B17 模板两入口同款 savepoint 范式。

### R5-B8 create_version IntegrityError 文案对齐（P3）

`views/admin.py create_version`：IntegrityError 分支文案改为「版本号或 PM 已占用」（与 update_version 一致）；既有测试补 message 断言。

### R5-B9 改期 purpose 非 str 拒绝（P3）

`services/slot_booking.py _resolve_target`：`raw_purpose` 非 None 且非 str → 抛 42201「purpose 必须为字符串」（拒绝优于 repr 化入库）；None/缺省 → 保留原值语义不变；str → 原 strip+长度校验逻辑不变。

### R5-B10 借用审批回避规则（P3，决策定案）

**决策：禁止自借自批，admin 亦不例外**（对照 cancel 端点「仅本人+admin 不例外」的既有审计取向；电子流的核心价值即审批留痕的独立性）。`views/borrow_flow.py _can_approve` 增加 `flow.borrower_id != user.id`，违反 → 40301「不可审批自己发起的借用」。reject 同受回避约束（驳回自己的申请无意义，应走 cancel）。

### R5-B11 check_build_mutex 时长单源（P3）

`services/mutex.py check_build_mutex`：删除函数内 `get_config("build_minutes")`，目标区间与既有策略区间统一用参数 `build_min`。调用方（validate_strategy 等）现传的就是 config 值，行为不变；补「传入非 config 值时两侧区间同源」单测。

### R5-B12 update_template 时长变更告警（P3）

`views/admin.py update_template`：当 smoke_minutes/analysis_minutes 发生变更时，对引用该模板的**启用策略**按分支分组做两两阶段重叠检测（复用 `services/mutex.py` 的区间计算逻辑抽出的纯函数），响应 `data.warnings` 返回冲突策略对清单（无冲突则空数组）。create_template 不做（新模板尚无引用）。前端 admin TemplatesTab 收到 warnings 时以 ElMessage.warning 展示。

### R5-B13 过滤参数 0 值 fail-closed（P3）

`views/strategies.py filter_strategies_qs`：`if version_id:` / `if branch_id:` 改为 `is not None` 判定（parse_int 失败返回 None 即「未提供」，0 则真过滤 → 空集），与 executions 的 strategy_id 语义统一。

## 二、前端修复设计

### R5-F1+R5-F12 数据中枢：最终写入守卫 + 四路并发（P2）

`views/panorama/useScheduleData.ts refresh()` 重排：

1. weekly 先行（版本回填逻辑不变，await 后 seq 守卫）；
2. calendars（monthsOf 后 Promise.all 多个月）、flows、todos、plan 四路并发：`Promise.allSettled` 或各自 try/catch 的并发组合——todos/plan 失败静默降级语义不变（todos 保留旧值、plan 空 Map），calendars/flows 失败仍走整体 catch；
3. 并发汇合后、构建 events 前补 `if (current !== seq) return true;`；最终 `events.value = all` 写入受守卫保护；
4. 文件头注释与实现一致（「weekly 先行 + 四路并发」）。

### R5-F2 借用复制文案三态分支（P2）

`views/borrow-flow/format.ts formatBorrowFlowText`：status 非 pending 时按三态——approved →「审批：{approver} 通过（意见） {handled_at}」；rejected →「审批：{approver} 驳回（意见） {handled_at}」；cancelled →「撤销：借用人撤销于 {cancelled_at}」（不拼审批人/意见）。字段以 `BorrowFlowItem` 实际类型为准（cancelled_at 若无类型字段则补）。

### R5-F3 策略页保存在途守卫（P2）

`views/strategy/index.vue`：`const saving = ref(false)`；onSave 入口 `if (saving.value) return`；confirm 通过后置位，finally 复位；按钮 `:loading="saving"`（disabled 条件保留）。

### R5-F4+R5-F15 seqGuard 工具 + 四页接线（P2）

新增 `src/utils/seqGuard.ts`：

```ts
/** 过期响应守卫：每次发起取新序号，settle 时校验是否仍为最新 */
export function createSeqGuard() {
  let seq = 0;
  return {
    next: () => ++seq,
    isCurrent: (token: number) => token === seq
  };
}
```

接线：branch-config `loadConfig`、slot-booking `load/setMonth`、RecordsPanel `load`、borrow-flow `load`、logs 四个 load（loadExec/loadChanges/loadOps/loadSecurity）——发起时 `const token = guard.next()`，写响应式状态前 `if (!guard.isCurrent(token)) return`。logs 页同时把 loadOps/loadSecurity 补共享 `loading` 置位。

### R5-F5 S4 折叠态外置（P3）

`s4-board/index.vue`：`const collapsedGroups = ref(new Set<string>())`；toggle 按 group.key 增删；模板 `:collapsed` 与展开箭头按 Set 派生；computed 输出不再携带 collapsed 字段、不被 mutate。

### R5-F6 S2/S5 锚点今天 + 去双拉（P3）

- s2-gantt/s5-timeline：`usePanoramaPage({ overrides: { dateFrom: today, dateTo: today } })`（无深链 query.date 时锚今天；有深链时用深链值作 overrides）；
- s5-timeline 删除 `watch(route.query.date, { immediate: true })` 回写 query 的双拉链，深链 date 直接进 overrides；「今天」按钮仍走总线 goToday。
- 既有 s2/s5 spec 的锚点断言同步更新（周一 → 今天/深链日）。

### R5-F7 S1 截断提示（P3）

热力图时刻 > 12：图表标题旁 tooltip/文案「仅展示前 12 个时刻（共 N 个）」；告警列表 > 8：列表尾「另有 N 条冲突未展示」。对齐 slotTruncated 外化范式。

### R5-F8 锚点日阶段事件过期口径（P3）

`sources/strategySource.ts phaseEvents`：`permissionsOf(strategy, past, ...)` 的 past 改传 `isPastSlot(date, s.build_start_time, now)`（与点事件同款判定），锚点日为今天时已结束策略行只读。

### R5-F9 report/detail 历史切换去双拉（P3）

`openHistory` 只做 `router.replace`（去掉手动 getReport 写值），数据加载全部交给既有 `watch(route.params.id)`；watch 内避免重复 loadHistory（history 列表加载与单报告加载分离，仅 id 变化时拉报告）。

### R5-F10 双 toast 收敛（P3）

report/index、StrategiesTab、detail onPublish 三处：catch 内 `isBizError(e)` 时不再补弹笼统文案（拦截器已弹真实 message），仅非 BizError（网络层/未知异常）兜底提示。

### R5-F11 token base64url（P3）

`utils/token.ts`：payload 先 `-`→`+`、`_`→`/`，按 mod 4 补 `=`，再 atob；try/catch 回退 8h 语义不变。

### R5-F14 借用弹窗回接（P3）

`weekly-new/components/StrategyBorrowDialog.vue` 创建成功后 emit `created`（weekly-new 侧不监听，零破坏）；`panorama/shared/ScheduleDialogs.vue` 接 `@created="data.refresh()"`。

### R5-F16 时段模板启停后重载（P3）

`slot-config/index.vue toggleEnabled`：成功后不再本地改写 `row.enabled`，finally 统一 `loadList()` 重载。

### R5-F17 死代码清理（P3）

删除 `selectors.ts` 的 `buildAgenda`/`agenda` 与 `useScheduleData.ts` 的 re-export，及 `selectors.spec.ts` 对应用例。

### R5-F13（记录在案）

borrow-flow/report/logs 三列表接入后端可选分页属功能增强（涉及 UI 分页条与查询状态管理），单独立项，不在本轮质量修复范围。

### R5-T1 vitest 超时固化

`vitest.config.ts` 补 `testTimeout: 15000, hookTimeout: 15000`。

## 三、回归测试设计

### 后端 `tests_quality_round5.py`（新增，覆盖缺口 1~13、15~16）

- `DisabledStrategyUpdateTests`：停用策略改名/改时间放行；漂移冲突策略 PATCH 停用放行且与 toggle 一致；PM 与 admin 两入口。
- `StrategyConflictPrecisionTests`：SQLite 字段名式 / PG 约束名式命中 40902 / 非目标约束 re-raise（mock IntegrityError 消息）。
- `AdminLogsMethodGuardTests`：POST/DELETE → 42201（并入 Round3 矩阵亦可，取其一，避免重复）。
- `LongUsernameReportTests`：150 字符用户名 builder 建报告/发布/留痕全链路不报错、落库无损。
- `ReportSnapshotEditTests`：策略改名/删除后报告仍可 PUT remark；快照字段变化时仍触发配对校验。
- `ReportUpdateFieldsTests`：update 后 status/publish_count/published_at 不回退（模拟陈旧实例）。
- `BranchConfigRaceTests`：permissions/projects 并发双提交 → 40903。
- `CreateVersionPmMessageTests`：PM 复用 → 40902 且 message 含「PM」。
- `ReschedulePurposeGuardTests`：非 str purpose → 42201，库存值不变。
- `BorrowSelfApprovalTests`：borrower==approver 审批/驳回 → 40301；admin 自批同样 40301；他人审批不受影响。
- `MutexBuildMinSourceTests`：check_build_mutex 传入非 config build_min 时两侧区间同源。
- `TemplateDurationWarningTests`：时长改大后 update_template warnings 命中冲突策略对；无冲突为空。
- `FilterZeroSemanticsTests`：version_id=0/branch_id=0/strategy_id=0 均返回空集。
- `UpdateVersionPmRaceTests`：PUT versions pm_user 已绑定 → 40902（缺口 14）。
- 截断上限与全角 month（缺口 15/16）视实现成本纳入。

### 前端（vitest）

- `format.spec`（borrow-flow）补 cancelled 三态用例；
- `useScheduleData` spec 补：乱序 settle 迟到不写回、plan 失败降级、并发拉取次数断言；
- `strategy` 保存守卫入 `adminSaveGuard.spec` 同款（或新 spec）；
- 新增 `utils/__tests__/seqGuard.spec.ts`；
- `utils/__tests__/token.spec.ts` 补 base64url 用例；
- 新增 `utils/__tests__/identity.spec.ts`（无 token 不发请求/失败不 reject/成功回写）；
- s4-board spec 补折叠保持用例；s2/s5 spec 更新锚点断言；
- selectors.spec 删除 agenda 用例。

## 四、验收标准

1. 后端 `python manage.py test build_protection_service` 全绿（≥ 500 例）；
2. 前端 `npm run test` 全绿（≥ 350 例）且 flaky 超时消除（testTimeout=15000）；
3. `npm run typecheck`、`npm run build` 通过；
4. migration 文件已生成并提交；
5. AGENTS.md 同步：第五轮报告索引、自借自批回避决策、seqGuard 工具、update_strategy 校验口径、tests_quality_round5.py 测试基线数；README 测试例数快照回改。
