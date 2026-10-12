# 第三轮代码质量优化实施计划（2026-10-13）

> 设计文档：`docs/superpowers/specs/2026-10-13-code-quality-optimization-round3-design.md`
> 评估报告：`docs/code-quality-assessment-2026-10-13.md`
> 纪律：每阶段完成后全量测试通过才进入下一阶段；禁止带失败提交。

## 阶段一：后端 P1（正确性 / 契约破坏）

- [x] R3-B1 auth.py 捕获 AuthenticationFailed，停用用户存量 token → 40100（+测试）
- [x] R3-B2 parse_body 非 dict 归一 + body_str 助手，login/borrow_flow/branch_config/reports 类型守卫（+测试）
- [x] R3-B3 时间序列化统一上海墙钟：fmt_dt/borrow_flow/slot_booking/branch_config/admin logs 加 localtime（+测试）
- [x] 阶段回归：后端全量测试通过（371 例 OK）

## 阶段二：后端 P2（并发 / 审计 / 一致性）

- [x] R3-B4 toggle 条件 UPDATE + 启用方向跑校验（+并发/互斥测试）
- [x] R3-B5 PM toggle/delete 写 StrategyChangeLog；delete 拦截 pending 借用流 40903（+测试）
- [x] R3-B6 update_user 角色/停用守卫绑定版本 40902（+测试）
- [x] R3-B7 config PUT parse_int + 非负校验（+测试）
- [x] R3-B8 seed get_or_create 去 status 锚点 + 幂等测试测量点修正
- [x] R3-B9 release_booking 条件 UPDATE（+测试）
- [x] R3-B10 list_strategies 可见性口径注释 + 测试锁定
- [x] 阶段回归：后端全量测试通过（371 例 OK）

## 阶段三：后端 P3 清理 + 测试补全

- [x] R3-B11 死代码清理（CODE_OK/不可达分支/未用 import/select_related/RevokedToken null 行）+ 分页助手收敛
- [x] R3-B12 security_log detail 截断 255（+测试）
- [x] R3-B13 密码最小长度 6 校验（+测试）
- [x] R3-B15 借用审批保留 push_mode/push_start_time（+测试）
- [x] R3-B16 读端点方法守卫 42201（+测试）
- [x] R3-B18 update_user 空密码串 → 42201（+测试）
- [x] R3-B14 测试缺口补全（executions 列表隔离、reports 分页、exception_handler 映射、slot_calendar 12 月边界、timeline sync 窗口、conclusion else、borrow_flow 404/模板已删/终态、template_applies_on 边界、_paginate 回退、add_branch 重名、ReportFilter 数字 keyword、services 各分支等）
- [x] 阶段回归：后端全量测试通过（371 例 OK）

## 阶段四：前端 P1

- [x] R3-F1 branch-config 轮询 disposed 守卫
- [x] R3-F2 StrategyDetailDialog 改判 push_mode === "sync"
- [x] R3-F3 RecordsPanel dateRange 默认值先于首次 load
- [x] 阶段回归：前端 vitest（156 例）+ typecheck 通过

## 阶段五：前端 P2

- [x] R3-F4 constants 新增 pushModeMeta/bookingStatusMeta + week.ts 星期常量，替换全部复制点（+测试）
- [x] R3-F5 动作路径 catch 统一 + 保存按钮 :loading（branch-config/StrategiesTab/VersionsTab/ConfigTab/StrategyEditDialog/StrategyBorrowDialog/report detail）
- [x] R3-F6 StrategyEditDialog 改走 adminApi.getTemplates
- [x] R3-F7 useWeeklyPanorama 删 WEEKDAY_CN 死映射 + timeRows 每行一次构建（+测试）
- [x] R3-F8 report/detail：setTimeout→nextTick、loadHistory 分页、base64Bytes/dataUrlToBlob 抽取 utils/screenshot.ts（+测试）
- [x] R3-F9 catch(e:any) 消除 + isBizError 守卫 + VersionItem.status 字面量联合 + loginByUsername 参数类型
- [x] R3-F10 getMe 启动时 silent 刷新身份快照
- [x] 阶段回归：前端 vitest（156 例）+ typecheck 通过

## 阶段六：前端 P3 清理 + 测试补全

- [x] R3-F11 P3 清理（dayjs 日期、死代码/死导出删除、formatTime 统一（先验证等价）、常量提取、loadMore 在途守卫、addEnv 空键守卫、pips 边界、welcome 文案、borrowFlowUrl 复用 appHashUrl）
- [x] R3-F12 测试补全（formatBorrowFlowText 分支、computeHourTrend 守卫+边界、computeTagCloud/computeKpis、http 40101/silent+401、useWeeklyPanorama seq 守卫/缓存、parseTime/formatTime 边界、tokenExpiresAt、screenshot.spec）
- [x] 阶段回归：前端 vitest（156 例）+ typecheck + build 通过

## 阶段七：收尾

- [x] 第二轮 spec 已勾选项全库 grep 交叉复核（防漏网），结果记录于本文档末尾
- [x] AGENTS.md 更新（测试基线、时间口径、catch 口径、可见性决策、第三轮文档索引）
- [x] 全量回归：后端 Django 测试 + 前端 vitest/typecheck/build 全绿
- [x] README 测试例数快照核对（如不一致以代码为准回改）

## 交叉复核记录（2026-10-13，阶段七）

针对第二轮"已勾选完成"项与本轮修复范式，全库 grep 复核，结果如下：

| 复核项 | 方法 | 结果 |
|---|---|---|
| 业务视图裸调 http（绕过 api 层，F-P2-6 同类） | grep `http.(get|post|...)` in views/ composables/ | ✅ 零残留（StrategyEditDialog 已改 adminApi） |
| push_start_time 三元猜测推送模式（F-P1-2 同类） | grep `push_start_time ?` in *.vue | ✅ 零残留 |
| 表格行内 el-switch v-model 乐观更新 | grep el-switch + v-model in views/ | ✅ 剩余 6 处均为**表单对话框本地字段**（form.enabled/auto_restart），不属表格行内开关范式约束范围，合规 |
| 手拼 `${origin}/#/` 深链接 | grep origin.*#/ | ✅ 仅 report/index.vue 一处命中且为注释，实际经 appHashUrl |
| `catch (e: any)` 残留 | grep catch any in 业务目录 | ✅ 零残留（命中均为说明注释），统一 isBizError 守卫 |
| 后端魔法错误码 `err(12345)` | grep err\([0-9]{5} | ✅ 零残留，全部走 errors.py 常量 |
| 手写 HTTP 状态码 | grep `status=[0-9]` in views/ services/ | ✅ 仅 json_resp 函数签名默认值一处，合规 |
| 手工 strftime 时区口径（B-P1-3 同类） | grep strftime 全后端逐点核对 | ✅ 所有 aware datetime 输出点均先 timezone.localtime；剩余裸 strftime 为 TimeField（%H:%M）、DateField、timeline naive 本地墙钟（datetime.combine 本地日期构建，无时区语义），合规 |
| 裸 `(x or "").strip()` 类型守卫（B-P1-2 同类） | grep 固定串全后端 | ✅ 剩余 9 处：slot_booking 3 处有 `str(...)` 包裹不会 AttributeError；report_service 5 处入参为 DRF serializer validated_data（CharField 已保证 str）；__init__.py 1 处为注释，均安全 |

结论：第二轮与本轮范式已无同类漏网点位。

## 全量回归与文档同步（阶段七完成情况）

- 后端 `python manage.py test build_protection_service`：**371 例全绿**（279 → 371，+92，超验收预期 ≥330）。
- 前端 `npm run test`：**156 例全绿**（124 → 156，+32，超验收预期 ≥150）；`npm run typecheck` 通过；`npm run build` 通过（2.79 MB）；`npm run lint:eslint` 通过。
- AGENTS.md 已同步：测试基线（371/156）、时间序列化口径（`fmt_dt` 上海墙钟唯一实现，R3-B3）、请求体守卫（`parse_body` 非 dict 归一 / `body_str`）与分页收敛（`paginate_qs`）、读端点方法守卫（R3-B16）、toggle/delete 服务层与审计（R3-B4/B5）、策略可见性设计决策（R3-B10）、借用推送配置复制（R3-B15）、admin 密码与 PM 绑定守卫（R3-B6/B7/B13/B18）、isBizError 与动作路径 catch 口径（R3-F5/F9）、工具层新增（identity/token/screenshot/weeklyReport）与星期数组唯一来源（R3-F4）、第三轮文档索引、策略周报模块补录。
- README 已同步：核心功能表补「策略周报」、测试例数快照（≥371/≥156）、文档索引补周报设计。
- 四份 feature spec 追加「修订记录（2026-10-13 第三轮质量优化）」：`2026-08-08-build-strategy-web-design.md`（含 toggle/DELETE 契约行内更新）、`2026-10-11-borrow-flow-design.md`（含 §2 决策表推送配置行更新）、`2026-10-10-slot-booking-design.md`、`2026-08-15-verification-report-design.md`。
