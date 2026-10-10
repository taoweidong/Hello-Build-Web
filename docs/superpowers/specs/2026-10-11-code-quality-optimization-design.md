# 代码质量优化设计（2026-10-11）

依据：`docs/code-quality-assessment-2026-10-11.md` 评估报告。本设计定义分阶段优化范围、关键决策与验收标准；配套 checkbox 实施计划见 `docs/superpowers/plans/2026-10-11-code-quality-optimization-plan.md`。

## 目标与不变量

**目标**：消除 P0 Bug 与安全隐患、统一错误处理与权限样板、补全前后端单元测试（后端覆盖全部端点与服务、前端建立 vitest 并覆盖 API 层/工具/composable）、收敛前端重复逻辑并拆分超大文件。

**不变量（优化中不得破坏）**：
1. 统一响应契约 `{code, message, data}`，code=0 成功；错误码语义固定（40100/40101 未认证、40301 无权限、40401 不存在、42201 参数非法、40901 策略时间冲突、40902 重名/互斥、40903 重复关联、40904 时段抢占冲突）。
2. 前端业务 API 一律走 `src/api/http.ts`（自动解包 `data`）。
3. 时间序列化 `"%Y-%m-%dT%H:%M:%S"`，时区 Asia/Shanghai。
4. 前后端直连（`VITE_API_BASE_URL=http://localhost:8000/api`），开发期 CORS 全开。
5. 种子数据幂等锚点（Version「27A」）与演示账号行为不变。
6. 所有既有合法行为回归不变（114 个既有后端测试除有意修正的行为外必须继续通过）。

## 关键设计决策

### 后端

- **D1 错误码常量化**：新增 `build_protection_service/errors.py`，定义错误码常量 + `CODE_STATUS` 映射 + `fail(code, message, data=None, status=None)` 辅助（status 缺省由映射决定，40901/40902/40903/40904→409、40100/40101→401、40301→403、40401→404、42201→422）。`api.py` 的 `ok()/err()` 保持兼容；视图逐步改用 `fail()`，行为（状态码与报文）与现状一致。
- **D2 logout 真拉黑**：新增 `RevokedToken` 模型（jti 唯一、expires_at、created_at）；`auth.JWTAuthentication` 验证成功后检查 jti 是否已吊销；`/auth/logout` 解析 Authorization 头中的 token 并登记吊销（按 exp 过期即自然失效，无需清理任务也可用；提供可选清理）。security_log 修复 username（从请求头解析前先认证）与 detail 参数。
- **D3 登录限流**：Django cache（LocMemCache）按 username 计失败次数，5 次/15 分钟内锁定；成功登录清零。轻量实现于 `views/login.py`，可测试。
- **D4 魔法日期治理**：`plan.py` 与 `strategies.py` preview 的默认日期改为 `timezone.localdate()`；`mutex.check_build_mutex` 的基准日参数化（默认今天）；`plan.py` 的 `conflict` 字段用 `services/conflict.find_conflicts` 真实计算（当日启用策略间的时间重叠）。
- **D5 HH:MM 校验**：`strategies.py` 校验正则后增加 0-23/0-59 范围校验（复用 `timeline.parse_hhmm`），非法返回 42201。
- **D6 模板删除 BUG**：`delete_template` 改捕 `ProtectedError`（`django.db.models`），保持 40901+409 报文不变。
- **D7 settings 安全默认**：`DEBUG` 默认 false、`ALLOWED_HOSTS` 从 env（默认 `["*"]` 保持开发可用，生产由 env 收紧）、新增 `JWT_SIGNING_KEY` env（缺省回退 SECRET_KEY）、`.env` 移出版本库（`git rm --cached`）并新增 `.env.example` 模板。CORS 保持全开但支持 env 覆盖（开发直连不变量 4）。
- **D8 策略写路径事务化**：策略创建/更新（PM 与 admin 两入口）包 `transaction.atomic`，将共用校验+创建逻辑收敛到 `services/strategies.py`（新增），消除 admin.py 对 strategy_views 私有成员的访问与复制粘贴。SQLite 下 atomic + 先查后写已消除大部分窗口，DB 级约束作为后续演进记录（不改契约）。
- **D9 校验与索引补齐**：`SlotTemplateSerializer.weekdays` 校验（0-6 逗号分隔）；数字 ID 过滤统一走安全解析（非数字→42201）；迁移新增 `ReportRevisionLog.report_id`、`VerificationReport.status` 的 `db_index`；`SlotBooking` 已有约束不动。
- **D10 运行期配置落库**：`services/config.py` 改为 DB 单行表 `RuntimeConfig`（key-value JSON）+ 内存缓存失效，写入持久化，重启不丢；`/admin/config` GET/PUT 行为不变。
- **D11 助手去重**：`views/__init__.py` 提供统一 `first_error`、`require_admin`、`fmt_dt`；`_ERR_STATUS` 由 D1 取代；`security_log` 支持 detail。
- **D12 N+1 缓解**：`build_branch_config` 用 prefetch 批量取实例；`start_instance` 加「同 branch_project 活跃实例唯一」的 partial UniqueConstraint（迁移），并发兜底。

### 前端

- **D13 vitest 测试基础设施**：引入 `vitest` + `@vue/test-utils` + `jsdom`，`package.json` 增加 `test`（vitest run）与 `test:watch`；`vitest.config.ts` 复用 vite 别名 `@`。
- **D14 http.ts 错误契约收敛**：失败路径 reject 标准化 `BizError`（携带 `code/message/httpStatus/raw`），保留现有弹窗行为；401 时同步清理 `build-user-info`；40902 兜底文案泛化（去掉报告业务措辞）；受影响调用点（`report/detail.vue`、`slot-booking/index.vue`）改用 `e.code`。
- **D15 类型收敛**：`types.ts` 新增 `Role`/`Conclusion`/`PushStatus`/`ReportStatus` 等字面量联合并替换 `string` 字段；删除 `branchConfig.ts` 内重复 `BranchItem`，统一从 `types.ts` 导出。
- **D16 共享常量与 composables**：新增 `src/views/constants.ts`（conclusionMap/pushStatusMap/stageStatusTypeMap 等单一来源）；`src/composables/useStrategyPreview.ts`（防抖+seq 守卫+冲突弹框）；`src/composables/useGanttRows.ts`（plan/versionView 共用的甘特行构建）；`panorama.ts` 复制函数改 re-export。
- **D17 安全与细节**：mock `enableProd` 关闭；登录表单预填口令仅开发环境（`import.meta.env.DEV`）；`el-switch` 改 `:model-value` + 失败回滚；BOM 清理；错别字修复；`execution/index.vue` 轮询加页面隐藏暂停与失败退避；welcome 页替换为业务概览入口卡片。
- **D18 死代码清理**：删除 `components/gantt/GanttChart.vue`、`business.ts` 死函数、`branch-config` 的 `openPermDialog`；`api/user.ts` 保留基座必需项并注明原因。
- **D19 大文件拆分**：`admin/index.vue` 按 Tab 拆为 `components/`（VersionsTab/UsersTab/TemplatesTab/ConfigTab/StrategiesTab）；`report/detail.vue` 抽 `composables/useReportForm.ts`（表单状态机/发布流程/截图校验）+ 演示假数据移入开发环境分支。拆分后行为不变，靠既有交互路径 + 新增单测守护。
- **D20 strict 不全局开启**：`tsconfig strict` 与 `no-explicit-any` 涉及 pure-admin 基座数百文件，本轮不动（记录为债务），新代码按 strict 风格书写。

## 阶段划分与验收标准

| 阶段 | 内容 | 验收 |
|---|---|---|
| 1 后端 P0 | D2/D3/D4/D5/D6/D7 + 对应新测试 | 后端全量测试通过；`.env` 不再被追踪；模板删除返回 40901 |
| 2 后端 P1 | D1/D8/D9/D10/D11/D12 + 测试补齐（admin templates 全 CRUD、users/versions 更新、logs/changes、round_detail、PM 策略 PATCH/toggle、logout 黑名单、限流、mutex 直测） | 后端测试 ≥ 160 且全绿；无跨模块私有访问 |
| 3 前端基建 | D13/D14/D15 | `npm run test` 可运行；http/BizError 有单测；typecheck 通过 |
| 4 前端收敛 | D16/D17/D18 + composables 单测 | 重复常量/逻辑单一来源；死代码删除；typecheck+test 通过 |
| 5 拆分 | D19 | typecheck+test+build 通过；页面交互回归 |
| 6 收尾 | AGENTS.md 测试纪律；全量回归；分阶段提交 | 后端+前端测试全绿；build 成功 |

## 风险与回滚

- 每阶段独立提交，出问题可按提交回滚。
- 行为变化点（需在提交说明中注明）：plan/preview 默认日期从魔法日期改为当天；plan.conflict 从写死 false 改为真实计算；logout 后 token 立即失效；登录连续失败 5 次锁定 15 分钟；运行期配置重启不丢。
- 迁移文件随阶段提交（仓库惯例）。
