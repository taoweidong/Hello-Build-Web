# 代码质量评估报告（2026-10-11）

> 评估范围：`backend/`（Django 5 + DRF + SimpleJWT + SQLite，约 5,000 行）与 `frontend/`（Vue 3 + Vite + TS + Element Plus，pure-admin-thin v6.2.0，业务视图约 9,000 行 + API 层约 1,000 行）。
> 评估方法：全量阅读视图/服务/模型/序列化器/API 层源码 + 现有测试盘点 + 配置与工具链审查。
> 基线状态：后端 114 个测试全部通过（1 个跳过）；前端 typecheck 通过；前端测试基础设施为零。

## 总体结论

项目整体分层意识良好（服务层下沉、统一响应契约、错误码语义固定、领域模型拆分清晰），slot-booking / branch-config / report 三个较新模块是内部最佳实践。但存在 **1 个已确认的功能性 Bug、1 个密钥泄漏、一批不安全默认值、权限与错误处理的双轨制、以及前端零测试** 等问题。按严重程度分述如下。

---

## 一、后端问题清单

### P0 — 功能性 Bug 与安全

1. **删除被引用模板必然 500（真 Bug）**：`views/admin.py:276-279` 捕获 `IntegrityError`，但 `Strategy.template` 为 `on_delete=PROTECT`（`models/others.py:62-64`），实际抛出的是 `ProtectedError` → 409 分支是死代码，删除被引用模板直接 500。因该模块零测试覆盖而未暴露。
2. **`.env`（含真实 SECRET_KEY）被 git 追踪**：`git ls-files` 确认 `backend/.env` 在版本库中，密钥已进入提交历史；`settings.py:11` 还有硬编码 fallback 密钥，且同一密钥兼作 JWT `SIGNING_KEY`（`settings.py:101`）——生产漏配环境变量时任何人可伪造 token。
3. **HH:MM 校验放行 `"99:99"`**：`views/strategies.py:62` 正则 `\d{2}:\d{2}` 不校验数值范围，`services/timeline.py:13-15` 随后抛 `ValueError` 未捕获 → 创建/预览策略直接 500。
4. **一组不安全默认值**：`settings.py` 中 `DEBUG` 默认 true（第 12 行）、`ALLOWED_HOSTS=["*"]`（第 13 行）、`CORS_ALLOW_ALL_ORIGINS=True`（第 104 行）、`AUTH_PASSWORD_VALIDATORS=[]`（第 68 行）、默认密码 `123456`（`views/admin.py:164`、`seed.py:30-34`）。
5. **logout 形同虚设**：`views/login.py:37-39` 不拉黑 token，JWT 8 小时有效无刷新/黑名单机制（`settings.py:84`）；且 `logout_view` 读取 `request.user`（普通视图未经 JWT 认证，恒为 AnonymousUser）→ 登出安全日志 username 恒为空。登录亦无失败限流。

### P1 — 架构一致性与正确性

6. **策略互斥校验无并发兜底**：`views/strategies.py:59-95` check-then-act，无事务、无 DB 约束，并发创建可产生互相冲突的策略（对比 `services/slot_booking.py:206-228` 有 `transaction.atomic` + partial unique + IntegrityError→40904 的正确做法）。
7. **运行期配置是假持久化**：`services/config.py:2` 的 `_RUNTIME_CONFIG` 进程内存 dict，admin 改的配置重启即丢、多 worker 不一致。
8. **魔法日期 `"2026-08-10"` 散布 4 文件 6 处**（`mutex.py:36,50`、`strategies.py:90,141`、`plan.py:16`）——preview/plan 不传日期时返回的全部时间线挂在这个假日期上；`plan.py:55` 的 `"conflict": False` 是写死占位，从未真实计算。
9. **权限体系双轨制**：全局默认 `IsAuthenticated`，但每个视图手动 `authed_user(request)` 并设 `permission_classes=[AllowAny]`（`views/__init__.py:34-42`，`views/reports.py:35-37` 注释自证）；`permissions.py` 的 `IsAdmin`/`IsPmOrAdmin` 全库零引用（死代码）。
10. **错误处理散乱**：错误码是裸魔法数字，code→HTTP 状态映射仅 `slot_booking.py:33-36` 集中一处，其余视图手写；`_first_error` 复制 3 份（branch_config.py:46、reports.py:51、slot_booking.py:44）、`_require_admin` 2 份、`_fmt` 2 份（logs.py:7、executions.py:13）、时间解析助手 3 份（timeline/conflict/mutex）。
11. **读路径写副作用 + N+1**：GET `/branches/<pk>/instances` 在读取时调用 `advance(inst)` 写库（`views/branch_config.py:231-234`）；`build_branch_config` 对每个关联逐个查询（`services/branch_config.py:162-166`）；`start_instance` check-then-create 竞态可产生双 STARTING 实例（60-67 行）。
12. **跨模块访问私有成员**：`views/admin.py:378,389,403,427,439` 直接调 `strategy_views._strategy_payload`/`_validate`；`_create_admin_strategy`（381-403）与 `strategies.create_strategy`（146-173）大段复制。

### P2 — 数据模型与细节

13. **索引缺失**：`ReportRevisionLog.report_id` 为无外键 IntegerField 且无索引（`models/report.py:48`），`revisions` 查询全表扫描；`VerificationReport.status` 同样无索引。
14. **校验缺口**：`SlotTemplateSerializer.weekdays` 完全未校验（"8,abc" 静默入库永不匹配）；`filter(id=body.get("project_id"))` 遇非数字 ID 抛未捕获 `ValueError` → 500（`branch_config.py:118,175,210` 等多处）。
15. **其他**：`release` 忽略 `serializer.is_valid()` 返回值（`slot_booking.py:178`）；分支项目关联创建无事务（`branch_config.py:180-184`）；`update_strategy` 变更日志只写"更新策略： {旧名}"无字段差异（`strategies.py:202-203`）；多列表固定 200 条无分页；`weekly.py:15` 返回英文星期名；`views/admin.py:25` `_admin_log` 裸吞异常；`security_log` 不接受 detail 参数导致 `SecurityLog.detail` 恒为空；`User.role`（小写）与 `BranchPermission.role`（大写）双命名体系。

### 现有测试盘点

| 文件 | 测试方法数 | 覆盖 |
|---|---|---|
| `tests.py` | 52（含 1 skip） | 模型/timeline/conflict/auth/策略 API/plan/weekly/admin 部分/executions/seed/report |
| `tests_branch_config.py` | 28 | 分支配置模块三层 |
| `tests_slot_booking.py` | 34 | 时段抢占模块（含并发 40904） |

**零覆盖端点**：`/admin/templates` 全模块 CRUD（P0 Bug 1 因此存活）、`/admin/versions/<vid>` PUT、`/admin/users/<uid>` PATCH、`/admin/logs/<kind>`、`/logs/changes`、`/executions/rounds/<rid>`、PM 侧策略 PATCH/toggle、`/branch-projects/<pk>` DELETE、`/auth/logout`、停用账号登录 403 路径；`services/mutex.py` 无直接单测；plan/weekly 的 PM 数据隔离未测。

---

## 二、前端问题清单

### P0 — 测试与类型基础设施

1. **零测试基础设施**：无 vitest/jest、无 test script、无任何 spec 文件，近 1 万行业务代码零回归保障。
2. **类型系统两道闸全开**：`tsconfig.json:6-7` `strict:false`；`eslint.config.js:81` `no-explicit-any: off`。`logs/index.vue:34-37` 的 `ref([])` 之类错误全部逃逸。

### P1 — 安全与契约

3. **生产启用 mock 服务器**：`build/plugins.ts:52` `enableProd: true`，生产构建中假 `/login` 端点仍可访问。
4. **登录页硬编码默认口令**：`login/index.vue:39-42` 预填 `admin/123456`。
5. **API 层错误契约不统一**：`api/http.ts` 成功路径解包返回 `data`，失败路径 reject 原始 axios error → 业务侧深取 `e?.response?.data?.code`（`report/detail.vue:279,458`、`slot-booking/index.vue:219`）；40902 的兜底文案写死报告业务（`http.ts:53`）；401 跳登录时不清 `build-user-info`（`http.ts:41`），存在旧身份残留。

### P2 — 重复、超大文件与遗留

6. **系统性重复**：`plan/index.vue` 与 `versionView/index.vue` 约 120 行甘特构建逻辑复制；`conclusionMap`×5、`pushStatusMap`×4、策略预览防抖×2（strategy/index.vue:108-129 vs admin/index.vue:339-364）；`panorama.ts` 复制 3 个 API 函数而非 re-export。
7. **超大文件**：`report/detail.vue` 1081 行（58 行发布状态机 + `initNewForm` 向生产表单预填演示假数据）；`admin/index.vue` 810 行（5 个 Tab 单文件、手写校验、`el-switch` 乐观更新失败无回滚 `admin/index.vue:617`）。
8. **双 HTTP 层与双用户状态源**：业务走 `api/http.ts` 但 `api/user.ts`、`api/routes.ts` 仍走基座 `utils/http`；Pinia store 与 localStorage `build-user-info` 并行，401 不清理业务身份。
9. **类型质量债**：`types.ts` 状态/角色字段全为 `string` 非字面量联合；`BranchItem` 同名双定义（`types.ts:110` vs `branchConfig.ts:11`）；32 处 `row as XxxItem` 断言；`admin.ts:68-78` 内联 `import()` 类型。
10. **遗留与细节**：`GanttChart.vue` 288 行死代码（已被 GanttGanttastic 替代）；`business.ts` 的 `dayStart`/`stageStatusTypeMap` 无引用；`branch-config/index.vue:387` `openPermDialog` 死代码；`welcome/index.vue` 仍是模板占位页；5 个业务文件带 UTF-8 BOM；`.env.production` 未定义 `VITE_API_BASE_URL`；`execution/index.vue:109-116` 30s 轮询无退避、页面隐藏不暂停；`panorama/index.vue:211` 错别字"执行实践全文区"。

### 做得好的方面（保持）

- slot-booking / slot-config / branch-config 模块组件化拆分规范，子组件普遍泛型 `defineProps<{}>()` + 完整 FormRules。
- 竞态防护意识好：weekly/plan/strategy 均有序号守卫丢弃过期响应。
- `api/types.ts` 注释详尽、与后端契约对齐度高；git 提交遵循中文 conventional commits。

---

## 三、优先级汇总

| 级别 | 后端 | 前端 |
|---|---|---|
| P0（Bug/安全） | 模板删除 500、`.env` 泄漏、99:99 500、不安全默认、logout 失效 | mock 生产启用、硬编码口令、零测试 |
| P1（架构/正确性） | 策略并发兜底、假持久化配置、魔法日期、权限/错误双轨、N+1 与副作用 | http 错误契约、双状态源、重复逻辑收敛 |
| P2（细节/债务） | 索引、校验缺口、分页、审计日志质量 | 大文件拆分、死代码、类型债、BOM/文案 |
