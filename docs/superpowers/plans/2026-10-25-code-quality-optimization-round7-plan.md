# 第七轮优化实施计划（2026-10-25）

> spec：`docs/superpowers/specs/2026-10-25-code-quality-optimization-round7-design.md`
> 执行纪律：每完成一个 Phase 重跑对应测试门禁，全绿才进入下一 Phase；任何失败先修复再继续。

## Phase 0：准备（已完成 2026-10-25）
- [x] 基线确认：后端 325 例 / 前端 264 例全绿
- [x] 评估报告落盘 `docs/code-quality-assessment-2026-10-25.md`
- [x] spec 落盘

## Phase 1：后端 P2 修复（R7-B1~B4）✅
- [x] R7-B1 parsing.py parse_int 多负号修复
- [x] R7-B2 toggle_strategy 事务内 select_for_update 重读 + docstring 修正（核对视图层使用返回值）
- [x] R7-B3 admin.py Version/Branch/StrategyTemplate 删除拦截 + SlotTemplate 删除 PROTECT 转可读
- [x] R7-B4 plan.py 删 status 死字段 + tests.py 断言同步
- [x] 门禁：`python manage.py test build_protection_service` 全绿

## Phase 2：后端 P3 修复（R7-B5~B12）✅
- [x] R7-B5 borrow_flow cancel 重取 + IntegrityError 双格式匹配
- [x] R7-B6 _change_desc 显式 null 留痕
- [x] R7-B7 停用账号 login_disabled 审计
- [x] R7-B8 exception_handlers 415/406 与 status_code 兜底
- [x] R7-B9 plan/weekly Version order_by("id")
- [x] R7-B10 seed.py 首块 transaction.atomic
- [x] R7-B11 SlotTemplate CheckConstraint + migration 0017 + admin save_model 校验
- [x] R7-B12 注释漂移批 + views/admin.py 方法守卫顺序 + slot_booking 死 import
- [x] 新增 `tests_quality_round7.py`（R7-B1~B11 回归）
- [x] 门禁：全量测试全绿 + `makemigrations --check` 干净

## Phase 3：前端修复（R7-F1~F15）✅
- [x] R7-F1 MyBookingsDrawer 挂载即开（onMounted + spec）
- [x] R7-F2 http.ts 40101 拆分支（+ http.spec）
- [x] R7-F3 silent 轮询不动 loading（+ spec）
- [x] R7-F4 canApproveBorrowFlow 回避分支（+ business.spec）
- [x] R7-F5 identity 同步基座 roles（+ identity.spec）
- [x] R7-F6 S4 状态分组 statusText（+ spec）
- [x] R7-F7 策略事件 versionName 透传（+ spec）
- [x] R7-F8 SlotDetailDialog 空态 + 自释放关闭（+ 组件 spec）
- [x] R7-F9 S2 删除无效开关
- [x] R7-F10 strategy 页死变量/注释 + StrategyEditDialog 校验对齐
- [x] R7-F11 基座死文件/死依赖清扫（逐项 grep 复核后删）
- [x] R7-F12 工程卫生（tsconfig/lintstagedrc/npm 收敛/error 菜单/双 next）
- [x] R7-F13 http.ts 三组前瞻护栏（+ http.spec）
- [x] R7-F14 types.ts 幽灵字段修正
- [x] R7-F15 plan.ts 幽灵参数 + weekly 注释 + 契约测试扩展
- [x] 门禁：`npm run test` + `npm run typecheck` + `npx eslint "src/"` 全清 + `npm run build`

## Phase 4：文档同步✅
- [x] AGENTS.md：AI 交互纪律确认（既有「必须先执行单元测试且全部通过才允许提交」保留）、第六轮→第七轮基线与范式更新（drawer/浮层挂载即开、toggle 重读、admin 根实体删除拦截、40101 前端口径、回避规则前端对齐）、round7 测试文件与报告索引
- [x] README.md 测试例数快照核对（以实际为准回改）
- [x] panorama 设计文档补 /plan 契约修订记录（R7-B4）
- [x] spec/plan 收尾勾选

## Phase 5：提交（见 git log）
- [x] commit 1：docs 第七轮报告 + spec/plan
- [x] commit 2：fix(backend) R7-B1~B12 + tests_quality_round7.py
- [x] commit 3：fix(frontend) R7-F1~F15
- [x] commit 4：docs AGENTS/README 同步第七轮基线
