# 第六轮代码质量优化实施计划（2026-10-24）

> spec：`specs/2026-10-24-code-quality-optimization-round6-design.md`；报告：`docs/code-quality-assessment-2026-10-24.md`。
> 每完成一批勾一项；涉及代码的批次，测试全绿才算完成。

## 阶段一：后端

- [x] B1. `admin.py`：SlotTemplateAdmin 注册 + `_ReadOnlyAdmin`（SlotBooking/BorrowFlow/审计三表只读）+ StrategyAdmin.delete_model/delete_queryset 路由 delete_strategy（R6-B1/B12）
- [x] B2. `services/strategies.py`：update_strategy 事务内 select_for_update 重读 + save(update_fields)（R6-B2）
- [x] B3. `services/strategies.py`：create_strategy 传 check_conflicts=enabled（R6-B3）
- [x] B4. `serializers/slot_booking.py` + `services/slot_booking.py`：StrictCharField + create_booking 非 str 拒绝（R6-B4）
- [x] B5. `services/slot_booking.py`：release_booking reason 非 str 拒绝 + 200 长度守卫（R6-B5）
- [x] B6. `models/others.py`：BorrowFlow.borrower PROTECT + makemigrations（R6-B6）
- [x] B7. `views/borrow_flow.py`：reason 改 check_str_len 42201（R6-B7）
- [x] B8. `views/panorama.py`：todos 排除 borrower=user（R6-B8）
- [x] B9. `views/login.py`：logout 仅有效 token 写审计（R6-B9）
- [x] B10. `views/__init__.py` client_ip 唯一来源 + login/security_log 接线（R6-B10）
- [x] B11. `services/slot_booking.py`：月份 year/mon isascii 硬化（R6-B11）
- [x] B12. 清理：删 require_admin、filters/ 目录、settings django_filters 两处配置（R6-B13/B14）
- [x] B13. 注释集群修正：strategies/errors/serializers/config/plan（R6-B15）
- [x] B14. 新增 `tests_quality_round6.py`（复用 Round4Fixture），覆盖 B1~B11 + 既有测试按新口径微调
- [x] B15. 后端全量回归：`python manage.py test build_protection_service` 全绿 + `makemigrations --check` 干净

## 阶段二：前端

- [x] F1. `eventActions.ts`：释放项条件并上 canReleaseOthers（R6-F1）+ spec 用例
- [x] F2. 五布局解构瘦身（s1/s2/s3/s4/s5 共 24 处）（R6-F2）
- [x] F3. eslint --fix 4 处格式错误并全量 lint 复跑（R6-F3）
- [x] F4. 删 week.ts isoWeek/buildMonthWeeks、slotCalendar.ts summarizeCalendar + 对应 describe（R6-F4）
- [x] F5. BookingDialog 成功关弹窗（R6-F5）+ 组件 spec
- [x] F6. useScheduleActions batchReleasing + S4 按钮 :loading（R6-F6）+ spec 断言
- [x] F7. strategy 页 onSave 三连校验 + onMounted 分支判定口径修正（R6-F7）+ saveGuard 扩展
- [x] F8. S2/S3 past slot 放行 openDetail（R6-F8）+ spec 断言
- [x] F9. moduleContract.spec 补 getPanoramaTodos（R6-F9）
- [x] F10. SlotDetailDialog.spec（释放确认/:loading/失败保留/改期转发）（R6-F10）
- [x] F11. 注释漂移清理 + slotTruncated 触发条件注释（R6-F11/F13）
- [x] F12. appUrl.spec 样例更新（R6-F12）
- [x] F13. 死文件清理（echarts.ts/RePureTableBar/ReCol/print.ts/preventDefault.ts/propTypes.ts/getLogin，逐一复核）（R6-F14）
- [x] F14. strategySource Role 收窄 + strategy 页 onMounted 并行（R6-F15）
- [x] F15. 前端全量回归：`npm run test` + `npm run typecheck` + `npm run build` + `lint:eslint` 全绿

## 收尾

- [x] G1. AGENTS.md：第六轮清单/测试基线数字/死代码教训入质量清单；确认「每次 AI 交互必须测试全绿才提交」纪律条目（R6 要求）
- [x] G2. README 口径核对（测试例数快照）
- [x] G3. 分批提交（docs → fix(backend) → fix(frontend) → docs），每次提交前对应测试全绿

## 实施期补充（2026-10-24 当日）

- [x] B16. views/strategies.py 改用 svc_update 返回值组装响应（R6-B2 配套接线，既有 3 例断言失败暴露）
- [x] F16. 三弹窗「挂载即开」初始化修复：StrategyEditDialog/BookingDialog watch 补 immediate、StrategyBorrowDialog 补 onMounted 兜底（R6-F10 组件测试实证发现）
- [x] 全量回归：后端 325 例全绿（294 基线 + 31 例 round6）、前端 264 例全绿（257 基线 + 7 净增）、typecheck/build/eslint 全过
