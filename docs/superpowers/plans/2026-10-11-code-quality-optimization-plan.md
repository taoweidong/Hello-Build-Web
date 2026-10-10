# 代码质量优化实施计划（2026-10-11）

配套设计：`docs/superpowers/specs/2026-10-11-code-quality-optimization-design.md`。
纪律：每完成一项勾选一项；每阶段结束运行后端 `python manage.py test build_protection_service` 与前端 `npm run test`，全绿才提交。

## 阶段 1：后端 P0（Bug/安全）

- [x] T1 修复 `delete_template` 捕获 `ProtectedError`（views/admin.py），补测试：删除被引用模板→40901、删除空闲模板→成功
- [x] T2 修复 HH:MM `"99:99"` → 42201（views/strategies.py 校验），补测试：越界小时/分钟
- [x] T3 settings 安全加固：DEBUG 默认 false、ALLOWED_HOSTS env 化、JWT_SIGNING_KEY 独立 env；`.env` 移出版本库 + 新增 `.env.example`
- [x] T4 logout 真拉黑：`RevokedToken` 模型 + `JWTAuthentication` 吊销检查 + `/auth/logout` 登记 + security_log 修 username/detail，补测试（登出后同 token 401、登出日志有用户名）
- [x] T5 登录失败限流（cache 5 次/15 分钟），补测试（第 6 次锁定、成功后清零）
- [x] T6 魔法日期治理：plan/preview 默认 `timezone.localdate()`、mutex 基准日参数化、plan.conflict 真实计算，补测试
- [x] T7 阶段回归：后端测试全绿，提交

## 阶段 2：后端 P1（规范化/补测试）

- [x] T8 新增 `errors.py`（错误码常量 + CODE_STATUS + fail()），slot_booking `_ERR_STATUS` 迁移至公共实现，行为不变
- [x] T9 新增 `services/strategies.py` 收敛创建/更新逻辑，admin.py 与 strategies.py 共用，消除跨模块私有访问与复制；策略写路径包 atomic
- [x] T10 views/__init__ 统一助手：`first_error`/`require_admin`/`fmt_dt`/`security_log(detail)`，替换三处 `_first_error`、两处 `_require_admin`、两处 `_fmt`
- [x] T11 迁移：`ReportRevisionLog.report_id`、`VerificationReport.status` 加 `db_index`；分支项目活跃实例 partial UniqueConstraint + `start_instance` 竞态兜底
- [x] T12 校验补齐：weekdays 校验（0-6）；数字 ID 安全解析（非数字→42201）；`release` 检查 `is_valid()`
- [x] T13 `RuntimeConfig` 落库持久化（key-value 单行表 + 缓存），`/admin/config` 行为不变，重启不丢
- [x] T14 update_strategy 变更日志记录字段差异
- [x] T15 测试补齐：admin templates 全 CRUD、versions PUT、users PATCH、admin/logs、logs/changes、round_detail、PM 策略 PATCH/toggle、branch-projects DELETE、停用账号登录 403、mutex/conflict/timeline 服务直测、实例并发约束、配置持久化
- [x] T16 阶段回归：后端测试全绿，提交

## 阶段 3：前端测试基建 + API 层

- [ ] T17 引入 vitest + @vue/test-utils + jsdom，配置 `vitest.config.ts` 与 `test`/`test:watch` scripts
- [ ] T18 http.ts 收敛：`BizError` 标准化 reject（code/message/httpStatus）、401 清理 `build-user-info`、40902 文案泛化；受影响调用点改用 `e.code`
- [ ] T19 单测：http.ts 拦截器（解包/错误码分支/401 清理）、`utils/business.ts`、api 层参数契约（mock http）
- [ ] T20 类型收敛：字面量联合类型（Role/Conclusion/PushStatus/ReportStatus 等）；`BranchItem` 单一来源
- [ ] T21 阶段回归：前端 test + typecheck 全绿，提交

## 阶段 4：前端收敛与清理

- [ ] T22 `views/constants.ts` 统一 conclusionMap/pushStatusMap 等；5 处/4 处复制点替换
- [ ] T23 `composables/useStrategyPreview.ts` 与 `useGanttRows.ts`；plan/versionView/strategy/admin 接入；panorama.ts 改 re-export
- [ ] T24 安全与细节：mock enableProd 关闭；登录预填仅 DEV；el-switch 失败回滚；BOM 清理；错别字；execution 轮询可见性暂停
- [ ] T25 死代码清理：GanttChart.vue、business.ts 死函数、openPermDialog；welcome 页业务化
- [ ] T26 composables 单测；阶段回归全绿，提交

## 阶段 5：大文件拆分

- [ ] T27 `admin/index.vue` 拆 5 个 Tab 子组件（components/），行为不变
- [ ] T28 `report/detail.vue` 抽 `composables/useReportForm.ts`，演示假数据移入 DEV 分支
- [ ] T29 阶段回归：test + typecheck + build 全绿，提交

## 阶段 6：收尾

- [ ] T30 AGENTS.md 增加「AI 交互纪律」：每次交互必须执行前后端单元测试，全部通过才可提交
- [ ] T31 全量回归：后端测试、前端 test/typecheck/build 全绿
- [ ] T32 评估报告与计划文档勾选状态同步，最终提交
