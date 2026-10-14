# 第四轮代码质量优化设计（2026-10-15）

> 依据：`docs/code-quality-assessment-2026-10-15.md`（第四轮全库复评）。
> 主线：**① 把已验证范式补齐到全部新路径（panorama 域 + admin 侧 + 三个新端点）；② 字符串长度校验系统性补全（为 Postgres 迁移铺路）；③ 新功能合入前过质量清单的纪律固化。**
> 纪律：每阶段完成后必须全量测试通过（后端 `python manage.py test build_protection_service`，前端 `npm run test` + `npm run typecheck`）才进入下一阶段；行为有变化的条目同步更新对应 spec 与 AGENTS.md；禁止带失败提交。
> 编号规则：R4-Bxx 后端、R4-Fxx 前端，对应评估报告 B4-xx / F-xx。回归测试集中在 `tests_quality_round4.py`（后端）与既有/新增 spec（前端）。

## 阶段一：后端「高」（契约破坏 / 功能性 bug）

### R4-B1 admin 删除策略补 pending 借用流拦截（修 B4-01）
- `services/strategies.py` 新增共享函数 `delete_strategy(s, operator, *, admin_log=None)`：事务内检查 `BorrowFlow.objects.filter(strategy=s, status="pending").exists()` → 抛 `StrategyValidationError`（40903 语义，复用既有「存在待审批借用流」文案）→ `s.delete()`。
- `views/strategies.py delete_strategy`（PM 路径）与 `views/admin.py _delete_admin_strategy` 均改调该共享函数；PM 侧保留 StrategyChangeLog、admin 侧保留 AdminOpLog（各自视图写，行为不变）。
- 测试（tests_quality_round4.py，下同）：admin 删除有 pending 借用流的策略 → 40903 且策略/借用流均存续；无 pending 时删除成功且 AdminOpLog 留痕；PM 路径回归不变。

### R4-B2 分支删除 ProtectedError 兜底（修 B4-02）
- `views/branch_config.py BranchViewSet.destroy`：`try: branch.delete() except ProtectedError: return fail_resp(CODE_ASSOCIATION, "分支存在抢占记录或借用流引用，无法删除")`（口径对齐 `admin.delete_template`）。
- 测试：分支有 SlotBooking → DELETE 40903；分支被 BorrowFlow.target_branch 引用 → 40903；无引用 → 删除成功（既有级联测试回归）。

### R4-B3 非 dict body 归一补齐两处漏网（修 B4-03）
- `views/slot_booking.py partial_update`：`body = request.data if isinstance(request.data, dict) else {}` 再传服务层。
- `views/branch_config.py permissions`：同款归一。
- 测试：`PATCH /slot-bookings/<id>` 与 `POST /branches/<id>/permissions` 传 `[1]`/`"str"`/`null` → 42201（缺参分支），绝无 500。

## 阶段二：后端「中」（并发 / 审计 / 一致性）

### R4-B4 conclusion note 走 body_str + max_len（修 B4-04）
- `views/executions.py`：`"note": body_str(body, "note", default=r.note or "", max_len=255)`（body_str 的 default 语义即「非 str 回退」；max_len 超长截断，与 security_log R3-B12 口径一致）。
- 测试：note 传对象/数字 → 保持原值（回退 default）；传 300 字符 → 入库 255。

### R4-B5 版本 PM 必须为启用用户（修 B4-05）
- `views/admin.py` create_version/update_version：`pm.role != "pm"` 校验旁增加 `not pm.is_active → 42201 "PM 用户已停用"`。
- 测试：指定停用 pm 用户建版本/改绑定 → 42201。

### R4-B6 login/logout 方法守卫（修 B4-06）
- `views/login.py`：`login_view`、`logout_view` 开头 `if request.method != "POST": return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")`。
- 测试：GET/PUT /auth/login、GET /auth/logout → 42201 且无 RevokedToken/SecurityLog 副作用。

### R4-B7 security_log username 截断（修 B4-07）
- `views/__init__.py security_log`：`username=(username or "")[:100]`（模型 max_length=100）。
- 测试：200 字符用户名登录失败 → SecurityLog 正常落库且 len(username)==100。

### R4-B8 抢占/改期 IntegrityError 精确匹配（修 B4-08）
- `services/slot_booking.py` create_booking/reschedule_booking：仿 `_raise_conflict_or_reraise` 范式——异常消息含 `uniq_slot_booking_active`（或字段组合 date/template_id）才转 `SlotConflictError`（40904），否则原样 re-raise。抽公共助手 `_raise_slot_conflict_or_reraise(exc)` 放同文件。
- 测试：撞目标约束 → 40904（既有并发测试回归）；构造撞其他约束（如 mock NOT NULL）→ 异常上抛不吞。

### R4-B9 config PUT 先全量校验后原子写入（修 B4-09）
- `views/admin.py config_view`：先循环校验三键（parse_int + 非负），全部合法后 `transaction.atomic()` 内统一 `set_config`；`services/config.set_config` 加 IntegrityError 兜底重试一次（并发 get_or_create 竞态）。
- 测试：`{"build_minutes":40,"push_minutes":"abc"}` → 42201 且 build_minutes 未变（原子性断言）。

### R4-B10 字符串字段 max_length 校验补全（修 B4-10）
- `body_str` 调用点按模型 max_length 补 `max_len`，超长 → 42201 拒绝（口径：**拒绝优于静默截断**，仅审计类日志字段截断）：
  - version name(100)、username(150)、display_name(100)、template name(100)（admin.py）
  - branch name(100)、repository_url(255)、description(500 按模型)（branch_config.py）
  - borrow_flow reason(500 按模型)；审批建策略拼接名防御 `[:200]`
- `body_str` 增加 `max_len` 超限行为参数或统一约定：传 max_len 时超长直接抛 ValueError → 视图转 42201（实现取最简路径，保持既有调用点兼容）。
- 测试：代表性端点各传超长串 → 42201；借用审批拼接名超长 → 入库 ≤200。

### R4-B11 django-admin 最小加固（修 B4-11）
- `bps/admin.py StrategyAdmin.save_model`：调用 `services.strategies.validate_strategy`（或等价校验），失败 `raise ValidationError` 阻止后台直改产生冲突数据。
- 部署清单（生产关闭/改名 admin、强口令、IP 白名单）记录在案，不在本轮代码改动。
- 测试：admin 后台 save_model 冲突数据被拒（直接调 save_model 断言 ValidationError）。

## 阶段三：后端「低」清理 + 测试补全

### R4-B12 全角数字拒绝（修 B4-12）
- `services/timeline.py valid_hhmm`：前置 `hhmm.isascii()`；`serializers/slot_booking.py validate_weekdays`：`part.isascii() and part.isdigit()`。
- 测试：`"２２:００"` → 校验失败；weekdays 含全角 → 校验失败。

### R4-B13 借用流列表可选分页（修 B4-13）
- `views/borrow_flow.py borrow_flow_list_view`：接入 `paginate_qs`（携带 page 参数返回 `{items,total,page,page_size}`，不携带保持全量数组——与 reports 列表向后兼容口径一致）。
- 测试：带 page/page_size、非法回退、上限 100；不带 page 返回数组（回归）。

### R4-B14 借用流单条响应路径 select_related（修 B4-14）
- create/approve/reject/cancel 响应前用带 `select_related(...)` 的 queryset 重取（复用 cancel 已有 `extra_queryset` 写法抽公共 `_flow_qs()`），断言查询数下降。
- 测试：`assertNumQueries` 锁定单条路径查询数。

### R4-B15 seed master 分支缺失守卫（修 B4-15）
- `management/commands/seed.py _seed_extra_strategies`：`if master27a is None: master27a = Branch.objects.create(version=v27a, name="master")`（对齐 tr527a/tr627a 守卫）。
- 测试：删除 master 分支后重跑 seed 不崩且补建。

### R4-B16 stop_instance 条件 UPDATE（修 B4-16）
- `services/branch_config.py stop_instance`：`Instance.objects.filter(id=inst.id, status__in=("STARTING","RUNNING")).update(status="STOPPED", ...)`，rowcount=0 视为已停（幂等返回），对齐 R3-B9 范式。
- 测试：STOPPED 实例重复 stop 幂等；并发窗口语义锁定。

### R4-B17 模板创建并发重名兜底（修 B4-17）
- `views/slot_booking.py SlotTemplateViewSet.create` 与 `views/admin.py create_template`：`try: ... except IntegrityError: return fail_resp(CODE_DUPLICATE, "模板名已存在")`。
- 测试：预置同名后绕过 validate 直撞约束（或直接 create 重名）→ 40902 而非 500。

### R4-B18 登录失败计数原子化（修 B4-18）
- `views/login.py`：`cache.add(fail_key, 0, timeout)` + `cache.incr(fail_key)`；注释修正为「滑动窗口 15 分钟」。
- 测试：连续 5 次失败第 6 次 42901（既有测试回归）；计数经 add+incr 路径。

### R4-B19 测试缺口补全（评估报告缺口清单 1-10）
- 上述各条目测试随修复落地；另补：SlotBookingCreateSerializer 与 create_booking 双写校验口径漂移锁定测试（同一非法载荷走两条路径断言同错误码）。

## 阶段四：前端「高」

### R4-F1 panorama 策略缓存失效 + 版本键控（修 F-H1）
- `useScheduleActions.ts`：缓存改为 `{ versionId, list }` 键控（versionId 不同即重拉）；返回对象暴露 `invalidateStrategyCache()`。
- `ScheduleDialogs.vue onSaved`：先 `actions.invalidateStrategyCache()` 再 `data.refresh()`；`usePanoramaPage`/各布局在 query.versionId 变化处调用 invalidate（或依赖键控自动失效，取实现最简者，测试锁定两种场景）。
- 测试：useScheduleActions.spec——编辑保存后重开弹窗预填新值；切版本后 openEdit 不报「获取失败」。

### R4-F2 批量释放他人条目收集原因（修 F-H2）
- `batchRelease`：确认框后若 `releasable` 含 `!e.mine && canReleaseOthers` 条目 → `ElMessageBox.prompt` 收集统一原因（inputValidator 必填），自己的条目传 ""；汇总消息按 ok/fail 分别用 success/warning。
- 测试：含他人条目时 prompt 被调且 reason 透传 releaseBooking；取消 prompt 中止；全失败 → warning 而非 success。

### R4-F3 UsersTab/TemplatesTab 补 :loading（修 F-H3）
- 两组件补 `saving` ref，保存函数 try/finally 置位，按钮 `:loading="saving"`（对齐 VersionsTab 范式）。
- 测试：组件级 spec 或按既有 admin Tab 测试路径锁定 saving 状态翻转。

## 阶段五：前端「中」

### R4-F4 ReportHeader 周日边界（修 F-M1）
- pips 的 today 判定改为「props.today 落在 [weekStart, weekStart+6] 内 → todayIndex = diff」，与 elapsed<7 解耦；整周已过去（today 在周后）仍无 today 标记（R3-F11 语义保留）。
- 测试：ReportHeader.spec 补「今天=周日」「今天=周一」「历史周」「未来周」四场景。

### R4-F5 copyText 走 utils/clipboard + 文案收敛（修 F-M2）
- `useScheduleActions.copyText` 改调 `utils/clipboard.copyText`；借用文案抽为 `views/borrow-flow/format.ts` 的 `formatBorrowCopyText(flow)`（或扩展现有函数），panorama 与 borrow-flow 复用同一实现。
- 测试：clipboard mock 成功/失败路径；文案函数纯函数 spec。

### R4-F6 星期文案唯一来源接线（修 F-M3、F-M5）
- s2-gantt/s5-timeline dayTitle：`ddd` 改 `WEEKDAY_CN_SUN[d.day()]` 拼接；`useScheduleData` 删除本地 `WEEKDAY_CN_MON` 副本改 import `utils/week`。
- `weekMondayOf` 从 useScheduleData 导出（或挪 utils/week.ts 为 `mondayOf(date)`）并补单测；s1/s4 的内联周一计算改用之（与 R4-F9 合并实施）。
- 测试：week.spec 补 mondayOf；布局 spec 断言 dayTitle 含中文星期。

### R4-F7 created_at 展示统一 formatTime（修 F-M4）
- RecordsPanel 表格列、MyBookingsDrawer、SlotDetailDialog 三处 `created_at` 改 `formatTime(row.created_at, "YYYY-MM-DD HH:mm:ss")`；将 `views/borrow-flow/format.ts` 的 `formatFlowTime` 上移/复用 `utils/business.formatTime`（评估报告建议，验证输出等价后统一）。
- 测试：utils/business.spec 补 formatTime 该格式断言；三处若有组件 spec 同步更新。

### R4-F8 权限/时长单一来源（修 F-M6）
- `strategySource.permissionsOf` 改调 `utils/business.canEditPanorama`；`slotSource` 删除私有 `durationOf` 改 import `strategySource.durationOf`（或将 durationOf 挪 selectors/types 层，取依赖方向最干净者）。
- 测试：sources.spec 断言对齐；canEditPanorama 既有单测不动。

### R4-F9 查询处理器收敛 usePanoramaPage（修 F-M7）
- `usePanoramaPage` 返回 `setVersion/setBranches/setScope/shiftBy/goToday`（内部用导出的 `mondayOf`）；五布局删除各自的 onVersionChange/onBranchChange/onScopeChange/shiftDay/goToday 副本改调总线。
- 测试：usePanoramaPage.spec（若无则建）覆盖五个 mutator；五布局既有组件 spec 回归。

### R4-F10 eventActions 补单测（修 F-M8）
- 新增 `views/panorama/__tests__/eventActions.spec.ts`：各权限位组合 → 动作清单、顺序即优先级、withCopyAction 仅 borrow 追加、空权限 → 空清单。

### R4-F11 改期弹窗在途守卫（修 F-M9）
- `useScheduleActions` 增 `rescheduling` 状态（reactive ui 或独立 ref 暴露），`confirmReschedule` try/finally 置位；ScheduleDialogs 改期按钮 `:loading`。
- 测试：双击仅一次 PATCH（mock 断言调用次数）。

## 阶段六：前端「低」清理 + 测试补全

### R4-F12 http.ts 401 跳转走 appHashUrl（修 F-L1）
- `window.location.href = appHashUrl("/login")`；http.spec 补断言。

### R4-F13 panorama/slot 域清理集（修 F-L2/L3/L4/L5/L7/L8/L9）
- groupByBranch：s2-gantt lanes 改调之（接线）或删除导出+spec（取接线，避免内联重复）；countPendingApproval 删除（含 spec 引用）；BorrowApprovalDrawer `handled` 事件接线（审批成功后 emit，父级刷新）或删除声明。
- autoRefreshMs：删除死选项（唯一调用方不传），visibilitychange 守卫随选项一并清理；或保留选项并加 `if (!autoMs) return`——取删除（YAGNI）。
- DEFAULT_HORIZON_DAYS：收敛到 `views/constants.ts` 导出，两处 import。
- horizonEndOf 改 dayjs：`dayjs().add(horizon, "day").format("YYYY-MM-DD")`；s1/s3 路由跳转改 `router.push({ path: "/panorama/timeline", query: { date } })`。
- monthsOf 超 3 个月：返回值附 truncated 标记，画布层 toast/角标提示「范围过大，仅展示前 3 个月抢占」（实现取最简：useScheduleData 暴露 slotTruncated，s2/s5 顶部 el-alert 或一次性 ElMessage）。
- borrow-flow 筛选补 cancelled 选项（文案取 constants.borrowStatusMeta）。
- StrategyEditDialog：增 `templatesLoaded` 标志区分「成功加载」与「降级」，降级时下次打开重试拉取。
- 测试：constants.spec 补 DEFAULT_HORIZON_DAYS/horizon 常量；useScheduleData.spec 补 monthsOf 截断标记；borrow-flow 组件/spec 补 cancelled 选项；demoData/布局 spec 回归。

### R4-F14 残留 any 清理（修 F-L6）
- http.ts 拦截器参数改 `AxiosResponse`/`unknown` + 收窄；login QuickGroup.color 声明为 EP tag type 联合去掉 as any；report/detail conclusionIconMap 改 `Record<string, Component>`。
- 验证：`npm run typecheck` 通过；http.spec 回归。

## 阶段七：文档与收尾

- AGENTS.md：更新测试基线数字；「AI 交互纪律」条目保留并强化（新增：新功能合入前对照质量清单自检——缓存失效/类型守卫/:loading/唯一来源/方法守卫/PROTECT 兜底/长度校验）；补充 tests_quality_round4.py 与第四轮报告/spec 索引；panorama 域新增约定（动作总线、缓存失效、mondayOf 唯一来源）写入对应条目。
- README.md：测试例数快照同步（如有出入）。
- 相关 feature spec 补修订记录（scheduling-panorama-design.md 等受 R4-F1/F2/F9 影响的章节）。
- 全量门禁：后端 `python manage.py test`（≥391+新增）+ 前端 `npm run test`（≥277+新增）+ `npm run typecheck` + `npm run build` 全绿后提交。
