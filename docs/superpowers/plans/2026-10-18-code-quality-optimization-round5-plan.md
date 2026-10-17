# 第五轮代码质量优化实施计划（2026-10-18）

> 对应 spec：`specs/2026-10-18-code-quality-optimization-round5-design.md`；评估报告：`docs/code-quality-assessment-2026-10-18.md`。按阶段推进，每阶段完成后跑对应门禁，全绿才进入下一阶段。

## 阶段一：后端修复（R5-B1~B13）

- [x] B1 `services/strategies.py`：validate_strategy 拆格式/冲突校验，update_strategy 仅结果态启用跑冲突校验
- [x] B2 `services/strategies.py`：_raise_conflict_or_reraise 补 PG 约束名匹配
- [x] B3 `models/report.py`：username 快照字段 100→150 + makemigrations
- [x] B4 `serializers/report.py`：配对/存在性校验仅在创建或快照字段变化时执行
- [x] B5 `services/report_service.py`：update 改 save(update_fields=...)
- [x] B6 `views/admin.py`：logs_view GET-only 守卫
- [x] B7 `views/branch_config.py`：permissions/projects 包 atomic+IntegrityError→40903
- [x] B8 `views/admin.py`：create_version IntegrityError 文案对齐「版本号或 PM 已占用」
- [x] B9 `services/slot_booking.py`：改期 purpose 非 str → 42201
- [x] B10 `views/borrow_flow.py`：_can_approve 增加自借自批回避（40301，admin 不例外）
- [x] B11 `services/mutex.py`：check_build_mutex 构建时长单源（参数）
- [x] B12 `views/admin.py`：update_template 时长变更附 warnings（复用 mutex 区间逻辑）
- [x] B13 `views/strategies.py`：filter_strategies_qs 0 值 fail-closed（is not None）
- [x] 新增 `tests_quality_round5.py` 回归测试（spec 第三节清单）
- [x] 门禁：`python manage.py test build_protection_service` 全绿（≥500 例）

## 阶段二：前端修复（R5-F1~F12/F14~F17 + R5-T1）

- [x] T1 `vitest.config.ts`：testTimeout/hookTimeout 15000
- [x] F1+F12 `useScheduleData.ts`：最终写入 seq 守卫 + weekly 先行四路并发
- [x] F2 `borrow-flow/format.ts`：cancelled 三态分支
- [x] F3 `strategy/index.vue`：saving 守卫 + :loading
- [x] F4+F15 新增 `utils/seqGuard.ts`；branch-config/slot-booking/RecordsPanel/borrow-flow/logs 接线；logs 补 loading
- [x] F5 `s4-board/index.vue`：折叠态外置 ref<Set>
- [x] F6 `s2-gantt`/`s5-timeline`：默认锚今天 + 深链 overrides 去双拉
- [x] F7 `s1-dashboard`：热力图/告警截断提示
- [x] F8 `sources/strategySource.ts`：锚点日 past 按 isPastSlot
- [x] F9 `report/detail.vue`：openHistory 去双拉
- [x] F10 report/index、StrategiesTab、detail onPublish：双 toast 收敛
- [x] F11 `utils/token.ts`：base64url 支持
- [x] F14 `StrategyBorrowDialog` created emit + ScheduleDialogs 接线
- [x] F16 `slot-config/index.vue`：启停后重载列表
- [x] F17 删除 buildAgenda/agenda 死导出与 spec 用例
- [x] 前端回归测试：format cancelled / useScheduleData 乱序+降级 / strategy 保存守卫 / seqGuard / token base64url / identity / s4 折叠保持 / s2s5 锚点更新
- [x] 门禁：`npm run test` 全绿（≥350 例）、`npm run typecheck`、`npm run build`

## 阶段三：文档与提交

- [x] AGENTS.md：第五轮报告/spec 索引、自借自批回避、seqGuard、update_strategy 口径、测试基线数
- [x] README：测试例数快照回改
- [x] 全景设计文档补第五轮修订记录（涉及 useScheduleData/S2/S5/S4/S1 行为变化）
- [ ] 提交：后端修复、前端修复、文档三个 commit（简体中文 conventional commits）
