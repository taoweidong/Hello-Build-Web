# 代码质量评估报告（2026-10-18，第五轮全库复评）

> 评估范围：`backend/`（Django 5 + DRF + SimpleJWT + SQLite，业务 app `build_protection_service`，约 1.34 万行）与 `frontend/src`（Vue 3 + Vite + TS + Element Plus，pure-admin-thin v6.2.0，约 2.88 万行）。第四轮（2026-10-15）之后无新增业务代码（HEAD=a5c06de 即第四轮文档提交），本轮为**全库复评**：重点挖掘前四轮遗漏的横切问题、校验口径缺陷、Postgres 迁移就绪度与测试基建问题。
> 评估方法：双路深度审查（后端全量通读 views/services/models/serializers/parsing/auth/errors/exception_handlers/seed/settings 并对关键疑点写临时探针测试实机验证；前端 api/composables/utils/views 逐域走查 + 交叉 grep 验证死代码与重复逻辑）；对照第三/四轮报告逐项核实 R3-B1~B18、R4-B1~B19、R4-F1~F14 均已落地（不重复报告）；高危项（R5-B1/B4、R5-F1/F2/F3）由主线逐一读盘复核确认。
> 基线状态：后端 `python manage.py test build_protection_service` 全绿（474 例）；前端 `npm run test` 332 例中存在**环境性 flaky**（vitest 默认 `testTimeout: 5000` 过紧，机器高负载并行时重型组件挂载测试偶发超时，单文件复跑全绿——见「三、测试基建」）。
> 与前四轮的关系：第一轮（10-11）约 5.5 分、第二轮（10-12）约 7 分、第三轮（10-13）约 7.5 分、第四轮（10-15）前后端各约 7.5 分，本轮 **后端约 8.0 分、前端约 8.0 分**——四轮治理后主链路扎实，未发现新的 Uncaught rejection 逃逸、僵尸轮询、注入、越权（角色/版本隔离矩阵复核无洞）、限流绕过或敏感信息泄露；问题集中在「已验证范式没有推广到最后一批点位」与一类前四轮从未暴露的**「校验过度」型功能缺陷**。

## 总体结论

本轮问题呈三个鲜明特征：

1. **「校验过度」首次成为主矛盾**（前四轮治理的注意力都在「漏拦」，本轮暴露的是「误拦」）：`update_strategy` 对停用策略仍按启用口径跑冲突校验——停用策略连改名都被 40902 锁死，且数据漂移后无法经 PATCH 停用止血（R5-B1，探针实证）；报告 PUT 每次全量重跑「策略必须存在」活校验，与「文本快照、不建外键」的领域设计自相矛盾——策略改名后报告永久不可编辑（R5-B4）。两者都是可稳定复现的功能缺陷。
2. **范式推广的「最后一批死角」**：R4-B8 的 IntegrityError 双格式匹配没有同步到 strategies 的原型助手（迁 Postgres 后并发冲突裸 500）；R4-B17 的 savepoint+IntegrityError 兜底没有推广到 branch_config 两个 check-then-create；R4-B10 的长度治理漏掉跨模型 username 快照（100 vs 150）；R3-B16 的方法守卫矩阵漏掉 `/admin/logs/<kind>` 一个读端点；前端的「seq 过期响应守卫」与「:loading 在途守卫」两个已验证范式在 branch-config 主配置路径、slot-booking、RecordsPanel、borrow-flow、PM 策略页保存等点位仍是空白。
3. **Postgres 迁移就绪度成为后端 P2 的共同主题**：消息格式匹配（R5-B2）、字段宽度错位（R5-B3）、读改写反模式（R5-B5）三处都指向「SQLite 宽容掩盖、迁 PG 即出事」，`config/settings.py` 注释已明确规划迁移，建议一并处置。

前端另有两处真实功能缺陷：借用复制文案把「已撤销」拼成「驳回」（审计文案失真，R5-F2）；全景数据中枢最终写入无 seq 守卫，迟到响应可覆盖新数据且要等下一轮轮询才自愈（R5-F1）。

**分级：P1 = 功能性 bug / 契约破坏（可稳定复现），P2 = 并发 / 迁移就绪度 / 竞态缺陷，P3 = 一致性 / 细节债务与建议。** 编号规则：R5-Bx 后端、R5-Fx 前端、R5-Tx 测试基建；「处置」列标明本轮修复或记录在案。对应 spec：`specs/2026-10-18-code-quality-optimization-round5-design.md`，后端回归测试集中在 `tests_quality_round5.py`。

---

## 一、后端问题清单（backend/build_protection_service，简写 bps/）

### P1（高）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R5-B1 | **update_strategy 对停用策略仍按「启用口径」跑冲突校验，合法操作被误拦**：不论目标态 `enabled` 为何一律调 `validate_strategy`（该校验按「即将启用」假设做互斥/阶段检测）。探针实证两个场景：① 停用 A(22:00) → 同分支建启用 B(22:00)（合法）→ A 改名 → 40902「资源互斥」，停用策略改名被永久锁死；② 模板时长改大致两条启用策略阶段重叠（R5-B12）后 `PATCH {"enabled": false}` 被 40902 拦——而 toggle 端点可以停用，同一操作两入口行为相反，update 入口恰好堵死「先停用归档再处理冲突」的官方逃生通道（R4-B11 注释推荐路径） | `bps/services/strategies.py:171-192` | 本轮修复：对齐 toggle 语义，仅结果态 enabled=True 才跑 validate_strategy |
| R5-B4 | **报告 PUT 每次全量重跑「策略必须存在」活校验，与快照设计自相矛盾**：报告域契约是「版本/策略/作者均为文本快照，不建外键」（`models/report.py` docstring 明言），但 `ReportSerializer.validate` 在 create 与 update 都强制 `Strategy.objects.filter(name=..., branch__version__name=...).exists()`。策略被改名/删除（常规操作）后，作者对报告的任何 PUT——哪怕只改 remark 一个错别字——都 42201「策略不属于所选版本」；且 publish 路径不重跑该校验，同一份「失效引用」发布可以、编辑不行，口径分裂 | `bps/serializers/report.py:84-89`、`views/reports.py:93-110` | 本轮修复：存在性校验仅在新建或 update 时快照字段发生变化才执行 |

### P2（中）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R5-B2 | **strategies._raise_conflict_or_reraise 只匹配 SQLite 消息格式**（R4-B8 未推广）：匹配条件 `"strategy.branch_id" in msg and "build_start_time" in msg`，Postgres 消息携带约束名 `uniq_active_strategy_branch_time` 不含该字样 → 不命中 → re-raise → 非 DRF 异常 → 裸 500 破坏契约。settings 已规划迁 PG，届时这层 DB 兜底是并发撞约束的唯一防线。slot_booking 版（R4-B8）已示范双格式匹配 | `bps/services/strategies.py:260-273` | 本轮修复：补约束名匹配 + 消息格式三件套单测 |
| R5-B3 | **报告域 username 快照字段宽 100，User.username 上限 150**（R4-B10 跨模型漏网）：`Report.created_by_username` / `ReportRevisionLog.operator_username` 均 max_length=100，服务层把 `user.username`（合法可达 150）原样写入。101-150 字符用户名建报告：SQLite 静默放行，迁 PG 即 DataError → 500，且每次留痕都写。与 R4-B7（SecurityLog 截 100）同族但这处连截断都没有 | `bps/models/report.py:24,54` | 本轮修复：出 migration 扩到 150（快照语义应无损）+ 锁定测试 |
| R5-B5 | **ReportService.update 全字段 save()，可回滚并发 publish 已提交的字段**：视图读出实例后 update 对全部字段 save；窗口期内同作者 publish（F() 原子自增+置 published）已提交时，陈旧内存值整体覆盖——status 打回 draft、publish_count 回退、published_at 清空；结论锁检查同样基于陈旧 status 可被绕过。publish 侧刚用 F() 修掉的丢更新被 update 侧重新引入，与「条件 UPDATE 抢占」纪律相悖 | `bps/services/report_service.py:56-84` | 本轮修复：save(update_fields=实际变更字段) |

### P3（低）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R5-B6 | `/admin/logs/<kind>` 漏 GET-only 方法守卫（R3-B16 约定唯一漏网读端点）：POST/DELETE 照常执行查询返回 200，guard 矩阵测试恰好没覆盖它 | `bps/views/admin.py:521-557` | 本轮修复 + 补进 Round3 guard 矩阵 |
| R5-B7 | branch_config 两个 check-then-create 竞态撞 unique 未捕获 → 500（R4-B17 未推广）：permissions 的 `update_or_create`（unique_together (branch,user)）与 projects 的 `exists()` 预检+create（(branch,project)），并发双击后到者 IntegrityError 裸 500 | `bps/views/branch_config.py:199-207,241-243` | 本轮修复：atomic+IntegrityError → 40903 |
| R5-B8 | create_version 把「PM 已被其他版本占用」（OneToOne 撞约束）误报为「版本号已存在」，用户改名重试仍失败无从定位；update_version 的「版本号或 PM 已占用」已是正确示范 | `bps/views/admin.py:94-97` | 本轮修复：对齐文案 + 测试补 message 断言 |
| R5-B9 | 改期端点 purpose 非字符串被 `str()` 强转为 repr 串入库（`{"purpose":{"a":1}}` → `"{'a': 1}"` 垃圾数据）；create 路径经序列化器 CharField 会拒绝，同一资源两条写路径口径不一 | `bps/services/slot_booking.py:349-352` | 本轮修复：非 str → 42201（拒绝优于静默转换） |
| R5-B10 | 借用电子流允许「自借自批」：`_can_approve` 不比对 `borrower_id != user.id`，PM/admin 均可审批自己发起的借用，审计留痕无法区分正常审批与自我交易，且无决策记录（对照 cancel 端点专门写了「admin 亦不例外」） | `bps/views/borrow_flow.py:94-97` | 本轮修复：增加回避规则（borrower==approver → 40301，admin 亦不例外），决策落 spec |
| R5-B11 | check_build_mutex 同一次校验里构建时长双来源：目标区间用参数 `build_min`、既有策略区间重新 `get_config`——调用方传入不同值时校验结果悄然失真，违背「唯一来源」纪律 | `bps/services/mutex.py:41,47-51,68` | 本轮修复：统一用参数 + 「传参生效」单测 |
| R5-B12 | StrategyTemplate 时长修改无联动校验/告警：smoke/analysis 分钟改大后，引用它的既有启用策略之间可立即出现阶段重叠而端点无提示（R5-B1 场景二的冲突制造源）；对照 SlotTemplate 已返回 overlap warnings | `bps/views/admin.py:404-442` | 本轮修复：时长变更时响应附 warnings（复用既有冲突检测） |
| R5-B13 | 过滤参数 0 值语义两个读端点相反：策略列表 `if version_id:` 把 0 当未提供 fail-open 返回全量，执行列表 `strategy_id=0` 真过滤返回空集；fail-open 违背本库对 PM 可见性的 fail-closed 取向 | `bps/views/strategies.py:64-69` | 本轮修复：统一 `is not None` 判定（0 → 空集） |

---

## 二、前端问题清单（frontend/src，业务代码为重点）

### P2（功能缺陷 / 竞态 / 纪律漏网）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R5-F1 | **全景数据中枢缺「最终写入」seq 守卫，迟到响应覆盖新数据**：`refresh()` 各段读取后都有 `if (current !== seq) return`，但最终 `events.value = all; lastLoadedAt.value = new Date()` 无任何守卫——旧请求在 await todos/plan 期间被新请求取代后仍用旧数据同步写回，覆盖新请求结果且要等下一轮轮询（最长 30s）才自愈 | `views/panorama/useScheduleData.ts:169-225` | 本轮修复 + 乱序 settle 单测 |
| R5-F2 | **借用复制文案把「已撤销」拼成「驳回」——审计文案失真**：`flow.status === "approved" ? "通过" : "驳回"`，2026-10-13 上线撤销功能后 cancelled 落入 else 分支，复制出的文本为「审批：- 驳回」（审批人为空、动作错误），借用人自己撤销却被记为「被驳回」；borrow-flow 列表页与 panorama 复制共用此函数，两处同病；spec 恰好没有 cancelled 用例 | `views/borrow-flow/format.ts:29-33` | 本轮修复：按 borrowStatusMeta 三态分支 + cancelled 用例 |
| R5-F3 | **策略配置页「保存策略」按钮无 :loading/在途守卫（四轮全部漏网）**：`onSave` 无 saving 状态，confirm 关闭后到网络返回前可再次点击 → 并发两次 createStrategy，第二次撞 40902（与 R4-F3 修掉的 UsersTab/TemplatesTab 完全同款）；同页 onToggle 有守卫、admin StrategiesTab 有守卫，唯独 PM 主策略页没有 | `views/strategy/index.vue:160-195,420-426` | 本轮修复 + 入 adminSaveGuard 同款测试 |
| R5-F4 | **「过期响应守卫」范式未推广，4 个页面加载函数可被慢响应错配覆盖**：branch-config `loadConfig`（快速切分支 A→B，A 的配置晚归覆盖 B 的详情；同文件实例轮询有守卫，配置主路径反而没有）、slot-booking `load/setMonth`（连点翻月旧月覆盖新月）、RecordsPanel `load`（筛选连改错配）、borrow-flow `load`（状态筛选快切同款） | 各文件见 spec | 本轮修复：抽 `utils/seqGuard.ts` 共用小工具四处接线 + 乱序单测 |

### P3（一致性 / 性能 / 细节债务）

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| R5-F5 | S4 分组看板折叠态挂在 computed 输出上（`collapsed: false` 内联 + 直接 mutate computed 结果），每轮轮询/刷新全部重置弹开，且属 Vue 反模式 | `views/panorama/layouts/s4-board/index.vue:96,194-213` | 本轮修复：折叠态外置 `ref<Set<string>>` + 保持性单测 |
| R5-F6 | S2/S5 单日视图首屏锚点是本周一而非今天（周三打开看到历史日需手点「今天」）；S5 深链入场 immediate watch + onMounted 整链双拉 | `s5-timeline/index.vue:153,191-199`、`s2-gantt/index.vue:184` | 本轮修复：默认锚今天、深链 date 走 overrides 去双拉 |
| R5-F7 | S1 两处静默截断无提示（热力图 `slice(0,12)`、告警 `slice(0,8)` 且 KPI 计数与列表条数不一致无「还有 N 条」），与 R4-F13 刚立的 slotTruncated 外化范式双标 | `s1-dashboard/index.vue:128,257` | 本轮修复：截断提示 |
| R5-F8 | 锚点日阶段事件权限恒按未过期计算：`permissionsOf(strategy, false, ...)` 硬传 past=false，今天为锚点时已开始/已结束的策略行仍带 canEdit/canBorrow，与非锚点日口径不一致（后端有兜底故降 P3） | `views/panorama/sources/strategySource.ts:79` | 本轮修复：按 isPastSlot 传入 |
| R5-F9 | report/detail 历史报告切换双拉：openHistory 手动 getReport 写值后 router.replace 又触发 watch 清空重拉（卡片闪空 + 重复请求 + 重复 loadHistory） | `views/report/detail.vue:370-385` | 本轮修复：openHistory 只做路由跳转，加载交给 watch |
| R5-F10 | 错误双 toast/吞具体错误：report/index、StrategiesTab 在拦截器已弹真实 message 后再补笼统 error；detail onPublish 对 BizError 也补「发布失败，请重试」连弹两条 | `report/index.vue:100`、`StrategiesTab.vue:72`、`detail.vue:311-317` | 本轮修复：BizError 分支静默，仅非契约异常兜底 |
| R5-F11 | JWT 过期解析不支持 base64url：`atob(payload)` 遇 `-`/`_`/无 padding 抛 InvalidCharacterError → 恒回退 8h 估算，后端调整时效或 payload 恰含这些字符时前端过期感知失真 | `utils/token.ts:6` | 本轮修复：base64url 归一 + 单测 |
| R5-F12 | 数据中枢 5 路请求全串行（weekly→calendars→flows→todos→plan 依次 await），flows/todos/plan 互不依赖可并发；与文件头注释及 AGENTS.md 宣称的「四路并发」不符，30s 轮询把串行 RTT 放大 3~4 倍 | `views/panorama/useScheduleData.ts:133-192` | 本轮修复：weekly 先行，其余四路 Promise.all + 各自 seq 守卫 |
| R5-F13 | 三处列表未接后端可选分页全量渲染（borrow-flow admin 视角、report、logs），后端 R4-B13 契约现成；数据积累后 el-table 无虚拟化会卡 | 各列表页 | **记录在案**（分页接线属功能增强，单独立项） |
| R5-F14 | 全景页发起借用成功后画面不刷新：ScheduleDialogs 的借用弹窗无 created 回接（同组 Booking/SlotDetail/MyBookings 都有），新事件最长延迟一个轮询周期 | `views/panorama/shared/ScheduleDialogs.vue:12-18` | 本轮修复：补 created emit + refresh 接线 |
| R5-F15 | 日志中心管理操作/安全日志两个 Tab 无 loading 反馈（loadExec/loadChanges 置共享 loading，loadOps/loadSecurity 不置），且四个 load 均无乱序守卫 | `views/logs/index.vue:98-121` | 本轮修复（守卫并入 R5-F4 工具） |
| R5-F16 | 时段模板启停成功后本地改写 `row.enabled` 而非重载列表，偏离「操作后重载」纪律，并发场景本地值可与服务端漂移 | `views/slot-config/index.vue:64-77` | 本轮修复：finally 重载 |
| R5-F17 | 死导出复现：`buildAgenda`/`agenda` 生产零调用却被 spec 锁定（R4-F13 刚清理过同类，此为漏网） | `views/panorama/selectors.ts:32-51`、`useScheduleData.ts:330` | 本轮修复：删除 |

---

## 三、测试基建（R5-T1）

**vitest 默认 `testTimeout: 5000` 过紧导致环境性 flaky**：`vitest.config.ts` 未显式配置超时；全量套件多 worker 并行时（首次运行 setup 累计 629s，机器争抢严重）panorama 重型组件挂载测试（真实 Element Plus + router + 多段 flushPromises）与示例页冒烟测试偶发突破 5s——两次全量运行分别失败 1 例/4 例且失败集合不同，单文件复跑与低负载重跑均全绿，确认非产品缺陷。**处置**：`vitest.config.ts` 设 `testTimeout: 15000`、`hookTimeout: 15000` 固化；纪律补充「全量红灯先单文件复跑甄别环境性超时」。

---

## 四、测试覆盖缺口清单

### 后端（对照现有 474 例，与问题一一对应者均零覆盖）

1. ★ 停用策略 update 路径（R5-B1）：同刻被启用策略占用时对停用策略改名/改推送时间 → 应 200；漂移冲突策略 `PATCH {"enabled": false}` → 应 200 且与 toggle 一致（PM 与 admin 两入口）
2. ★ `_raise_conflict_or_reraise` 消息匹配三件套（R5-B2）：SQLite 字段名式命中 / PG 约束名式命中 / 非目标约束 re-raise
3. ★ `POST/DELETE /admin/logs/<kind>` → 42201（R5-B6，Round3 guard 矩阵补行）
4. ★ 用户名 101-150 字符的 builder 创建/发布报告不截断不报错（R5-B3）
5. ★ 策略改名/删除后引用它的报告仍可 PUT 其他字段；配对校验仅在快照字段变化时触发（R5-B4）
6. ReportService.update 与 publish 交错不回退 status/publish_count/published_at（R5-B5）
7. permissions/projects 并发双提交 → 40903 非 500（R5-B7）
8. create_version PM 复用场景 message 断言（R5-B8）
9. `PATCH /slot-bookings/<id>` 传非 str purpose → 42201 不入库 repr 串（R5-B9）
10. 借用流 borrower==approver 自批 → 40301（R5-B10 决策锁定）
11. check_build_mutex 传入非 config 的 build_min 时目标与既有区间同源（R5-B11）
12. 模板时长改大后 update_template warnings 内容（R5-B12）
13. `?version_id=0`/`?branch_id=0`/`?strategy_id=0` 三端点语义一致性（R5-B13）
14. `PUT /admin/versions/<vid>` pm_user 改为已绑定 PM 的 IntegrityError 兜底分支（存量缺口）
15. executions/logs 200 条截断上限边界（存量缺口）
16. slot_calendar month 全角数字入参归一化（存量缺口）

### 前端（对照现有 40 spec / 332 例）

1. ★ `borrow-flow/format.ts` cancelled 分支（R5-F2 的 bug 正因此漏网）
2. ★ `useScheduleData` 乱序 settle：迟到 refresh 不写回 events；getPlan 失败降级分支（R5-F1/F12 锁定）
3. ★ strategy 页保存在途守卫（R5-F3，入 adminSaveGuard 同款；StrategiesTab 的 savingStrategy/toggling 守卫也未测）
4. ★ `utils/seqGuard` 工具单测 + branch-config/slot-booking/RecordsPanel/borrow-flow 乱序接线验证（R5-F4）
5. `utils/token.tokenExpiresAt` base64url payload 用例（R5-F11）
6. `utils/identity.refreshBusinessUser`：无 token 不发请求、失败永不 reject、成功回写（零测试）
7. s4-board 折叠态在数据刷新后的保持（R5-F5）
8. report/detail 发布链路与 openHistory（组件级零测试，本轮仅补纯逻辑可测部分）

---

## 五、结论与评分

| 维度 | 第四轮 | 第五轮 | 说明 |
|---|---|---|---|
| 后端 | 7.5 | **8.0** | 主链路扎实；本轮 13 项无一击即溃的 P0，两个 P1 均为「校验过度」型功能缺陷（其一探针实证），三个 P2 共同指向 Postgres 迁移就绪度 |
| 前端 | 7.5 | **8.0** | 四轮范式执行到位无回归；剩余问题为范式死角（seq 守卫/:loading）、两处真实缺陷与 panorama 细节债务 |
| 测试基建 | — | flaky 已定位 | vitest 默认 5s 超时不足，本轮固化 15s |

修复完成后预期：后端 ≥ 500 例（新增 `tests_quality_round5.py`）、前端 ≥ 350 例；R5-B1~B13 全部修复、R5-F1~F12/F14~F17 修复、R5-F13 记录在案。
