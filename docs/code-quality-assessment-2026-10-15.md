# 代码质量评估报告（2026-10-15，第四轮全库复评）

> 评估范围：`backend/`（Django 5 + DRF + SimpleJWT + SQLite，业务 app `build_protection_service`）与 `frontend/src`（Vue 3 + Vite + TS + Element Plus，pure-admin-thin v6.2.0）。重点覆盖第三轮（2026-10-13）之后新增的约 9100 行代码：调度全景（panorama）五布局模块、后端聚合端点（`/panorama/todos`、抢占改期 PATCH、借用撤销 cancel）、示例菜单占位页与登录快速按钮。
> 评估方法：全量通读后端 views(13)/services(8)/models(4)/serializers(3)/filters/parsing/errors/api/exception_handlers/settings/seed 与 9 个测试文件；前端 api/composables/utils/views（panorama 域逐文件）走查 + 交叉 grep 验证死代码与重复逻辑；对照第三轮报告逐项核实 R3-B1~B18、R3-F1~F12 均已落地（不重复报告）；高危项（B4-01/02/03、F-H1/H2/H3、F-M1）已由主线逐一读盘复核确认。
> 基线状态：后端 `python manage.py test build_protection_service` 391 例全绿；前端 `npm run test` 277 例（33 文件）全绿；工作区仅 `backend/uv.lock` 未跟踪（uv 生成的锁文件，见「其他观察」）。
> 与前三轮的关系：第一轮（10-11）约 5.5 分、第二轮（10-12）约 7 分、第三轮（10-13）约 7.5 分，本轮 **后端约 7.5 分、前端约 7.5 分**——存量主链路保持第三轮修复后的水准，问题几乎全部集中在第三轮之后**未经质量审查的新增代码**（panorama 域与三个新后端端点）。

## 总体结论

第三轮建立的范式（条件 UPDATE 抢占、body_str 类型守卫、fmt_dt 时间口径、方法守卫、BizError/受控开关/:loading 纪律、展示映射唯一来源、纯函数抽取+单测）在存量代码上执行扎实，本轮未发现新的 Uncaught rejection 逃逸或轮询僵尸。问题呈一个鲜明特征：

**「范式没有推广进新模块」**——第三轮之后落地的调度全景五布局与后端三个新端点是本轮问题的绝对主战场：

1. **后端**：admin 删除策略绕过 pending 借用流拦截（R3-B5 只修了 PM 路径）、分支删除撞 PROTECT 外键裸 500、非 dict body 500 集群仍有两处漏网（R3-B2 镜像）、新 PATCH 改期端点把 `request.data` 直塞服务层；外加一类**系统性债务**——字符串字段普遍缺 max_length 校验（SQLite 宽容掩盖，迁 Postgres 即成片 500）。
2. **前端**：panorama 域自带一套「影子实现」——策略详情缓存无失效且不区分版本（weekly 页已有 invalidate 范式）、复制绕过 `utils/clipboard`、星期数组本地复制、权限判定/时长计算重复实现、五布局各自复制同组查询处理器、`eventActions.ts` 是唯一没有 spec 的 panorama 纯函数模块。
3. **功能性缺陷**：批量释放对「他人抢占」恒失败（空 reason 撞后端必填校验）；ReportHeader 周日当天「今天」呼吸圈消失（R3-F11 修复引入的边界回归）；UsersTab/TemplatesTab 保存缺 `:loading` 双击重复提交。

**分级：高 = 功能性 bug / 契约破坏（可稳定复现），中 = 并发 / 审计 / 一致性缺陷，低 = 细节债务与建议。** 编号规则：B4-xx 后端、F-Hx/F-Mx/F-Lx 前端；「处置」列标明本轮修复（→ 对应 spec 条目 R4-Bxx/R4-Fxx）或记录在案。

---

## 一、后端问题清单（backend/build_protection_service，简写 bps/）

### 高

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| B4-01 | **admin 删除策略绕过「pending 借用流拦截」**（R3-B5 只修了 PM 路径）：`_delete_admin_strategy` 直接 `s.delete()`，`BorrowFlow.strategy` 为 CASCADE——admin 删除会静默抹掉进行中的待审批电子流（借用人/审批人无感知），同时级联删全部 ExecutionRound 历史。admin 入口反而比 PM 入口约束更松 | `bps/views/admin.py:574-580`（对照 `views/strategies.py:227-231` 的 PM 拦截） | 本轮修复 R4-B1 |
| B4-02 | **删除分支撞 PROTECT 外键 → 未处理 ProtectedError → 裸 500 破坏响应契约**：`SlotBooking.branch` 与 `BorrowFlow.target_branch` 均 PROTECT，分支有过抢占记录或被借用流指向时 `branch.delete()` 抛 `ProtectedError`（DatabaseError 子类，contract_exception_handler 返回 None）→ Django 默认 500，前端拿不到 `{code,message,data}`。同库 `admin.delete_template` 已正确处理，此处漏网 | `bps/views/branch_config.py:130-143` | 本轮修复 R4-B2 |
| B4-03 | **非 dict JSON body 的 500 集群仍有两处漏网**（R3-B2 镜像）：① 改期端点 `reschedule_booking(booking, user, request.data or {})` 直塞服务层，body 为非空 JSON 数组（`[1]`）时 `payload.get("date")` → AttributeError 500；② `permissions` action `body = request.data or {}` 同款。同文件 create/projects 均已用 `isinstance(request.data, dict)` 归一 | `bps/views/slot_booking.py:158`、`services/slot_booking.py:304`、`views/branch_config.py:209-210` | 本轮修复 R4-B3 |

### 中

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| B4-04 | **conclusion 的 `note` 绕过 body_str 约定**：`body.get("note", ...)` 直接进 `update(**fields)`，传对象存成 `"{'a': 1}"` 垃圾数据、超 255 字符迁 Postgres 即报错（R3-B12 同类）；全项目字符串提取「一律 body_str」的唯一漏网 | `bps/views/executions.py:117` | 本轮修复 R4-B4 |
| B4-05 | **create_version/update_version 可把停用用户设为版本 PM**：只校验 `role != "pm"` 不校验 `is_active`，与 R3-B6 守护的「无主版本」不变量形成反向漏洞 | `bps/views/admin.py:75-80,132-136` | 本轮修复 R4-B5 |
| B4-06 | **`logout_view`/`login_view` 无方法守卫**：`GET /auth/logout` 带 Bearer 头即吊销当前 token 并写审计日志（预取/爬虫/地址栏访问误杀会话），违反「写端点禁止 GET 产生副作用」约定（R3-B16 已覆盖其余写端点）；login GET 落入「用户名与密码不能为空」语义错位 | `bps/views/login.py:44,71-94` | 本轮修复 R4-B6 |
| B4-07 | **security_log 的 username 未截断**：`SecurityLog.username` max_length=100，login 的 username 取自请求体无 max_len——200 字符用户名反复登录失败，SQLite 放行、迁 Postgres 后安全日志整体丢失（审计致盲） | `bps/views/__init__.py:108-110`、`views/login.py:56,61,67` | 本轮修复 R4-B7 |
| B4-08 | **抢占/改期 IntegrityError 兜底过宽**：不区分约束一律 40904「被他人抢占」，撞 NOT NULL/外键失效/并发删除时用户收到误导性冲突提示；同库 `_raise_conflict_or_reraise` 已示范「按消息匹配目标约束、否则 re-raise」正确范式 | `bps/services/slot_booking.py:247-256,378-385` | 本轮修复 R4-B8 |
| B4-09 | **config_view PUT 多键更新非原子**：循环内逐键 `set_config` 独立提交，`{"build_minutes":40,"push_minutes":"abc"}` 时第一键已生效第二键才 42201，配置进入半套中间态；`set_config` 的 update_or_create 并发撞 key unique → 500 无兜底 | `bps/views/admin.py:437-450`、`services/config.py:21-24` | 本轮修复 R4-B9 |
| B4-10 | **写端点普遍缺 max_length 校验**（系统性）：version name(100)/username(150)/display_name(100)/branch name(100)/repository_url(255)/template name(100) 等 `body_str` 调用点几乎都未传 `max_len`；借用审批建策略拼接名 `f"...(...借用)"` 可超 Strategy.name 的 200。SQLite 静默放行，迁 Postgres 全部变 500 | `bps/views/admin.py:70-73,198-216,320-336`、`views/branch_config.py:114-125`、`views/borrow_flow.py:195-207` | 本轮修复 R4-B10 |
| B4-11 | **django-admin 后台可绕过全部服务层校验直接改业务数据**：StrategyAdmin 允许后台直改 build_start_time/enabled/push_mode 不经互斥/阶段校验；生产（DEBUG=false）面板仍暴露且 seed 默认口令 admin/123456 | `bps/admin.py:29-36`、`config/urls.py:6` | 本轮做最小加固 R4-B11（save_model 走服务层校验）；部署清单项记录在案 |

### 低

| 编号 | 问题 | 处置 |
|---|---|---|
| B4-12 | `valid_hhmm`/`validate_weekdays` 接受 Unicode 全角数字（`\d` 匹配 `２２:００`），与 `parse_int` 的 isascii 硬化口径不一；全角时间串入库后字符串排序错位 | 本轮修复 R4-B12 |
| B4-13 | 借用流列表无分页/条数上限：admin 视角全量返回所有历史电子流，与「分页统一 paginate_qs」约定不符 | 本轮接入可选分页 R4-B13（参照 reports 向后兼容做法） |
| B4-14 | 借用流 create/approve/cancel 单条响应路径固定 N+1：`_payload(flow)` 访问 6+ 关联未 select_related（列表路径已正确配置） | 本轮修复 R4-B14 |
| B4-15 | seed：27A master 分支被删时 `_seed_extra_strategies` 用 None 分支 get_or_create → IntegrityError 整个 seed 中断；tr527a/tr627a 均有「缺失即补建」守卫，唯独 master 没有 | 本轮修复 R4-B15 |
| B4-16 | `stop_instance` 读改写无条件 UPDATE，与「条件 UPDATE + rowcount」并发范式（R3-B9）不一致 | 本轮修复 R4-B16 |
| B4-17 | `SlotTemplateViewSet.create`/admin `create_template` 并发重名 → 未捕获 IntegrityError → 50000/500 而非契约 40902（对照 users_view/create_version/add_branch 均已包） | 本轮修复 R4-B17 |
| B4-18 | 登录失败计数非原子自增：`cache.set(key, cache.get(key,0)+1)` 读改写三步，并发爆破可稀释 5 次阈值；且每次失败刷新 TTL，实际是「滑动 15 分钟」与注释「连续失败 5 次锁定 15 分钟」不符 | 本轮修复 R4-B18（add+incr 原子化 + 注释修正） |

### 后端测试覆盖缺口（与上述问题一一对应，均零覆盖）

1. ★ admin `DELETE /admin/strategies/<id>` 存在 pending 借用流场景（B4-01；tests.py:513 只测无引用删除）
2. ★ `DELETE /branches/<id>` 分支被 SlotBooking/BorrowFlow 引用（B4-02；现只测角色门槛与级联成功路径）
3. ★ `PATCH /slot-bookings/<id>`、`POST /branches/<id>/permissions` 非 dict JSON 载荷（B4-03）
4. ★ conclusion note 传数字/对象/超 255 字符（B4-04）
5. create_version/update_version 指定 `is_active=False` 的 pm 用户（B4-05）
6. `GET /auth/logout`（B4-06；现有 logout 测试全部 POST）
7. 超长 username 登录失败写 SecurityLog（B4-07）
8. `POST /admin/config` 多键部分非法时的最终落库状态断言（B4-09）
9. 全角数字 build_start_time/weekdays 入参（B4-12）
10. `SlotBookingCreateSerializer` 与 `create_booking` 双写校验的「口径漂移」锁定测试（第三轮记录在案项，至今无守卫）

---

## 二、前端问题清单（frontend/src，业务代码为重点）

### 高

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| F-H1 | **全景页策略详情缓存永不失效、且不区分版本**：`strategyCache` 为模块级 `let`，`loadStrategyDetails(versionId)` 入参不参与缓存判定，全链路无 invalidate——① 编辑保存后 `onSaved` 只 `data.refresh()`，再开编辑弹窗仍用旧缓存预填（旧时间/旧名称）；② 切版本后旧缓存 `find` 不中 → 误报「策略详情获取失败」。weekly 两页已有 `invalidateStrategyCache()` 范式，panorama 未推广 | `views/panorama/useScheduleActions.ts:74-83`、`shared/ScheduleDialogs.vue:111-113` | 本轮修复 R4-F1 |
| F-H2 | **批量释放对「他人抢占」恒失败**：过滤纳入 `canReleaseOthers`（admin 释放他人），循环里统一传空 reason，而后端规定非 owner 释放必填原因（42201）——admin 勾选他人抢占批量释放逐条静默失败，只弹「成功 0 条，失败 N 条」无原因说明；且全部失败也走 `ElMessage.success` | `views/panorama/useScheduleActions.ts:337-375` | 本轮修复 R4-F2 |
| F-H3 | **UsersTab/TemplatesTab 保存按钮缺 `:loading`、无在途守卫**：双击并发两次 create，第二次撞 40902 重名弹错；同目录 VersionsTab/StrategiesTab/ConfigTab 均已按纪律加守卫，这两个 Tab 漏网 | `views/admin/components/UsersTab.vue:43-75,191`、`TemplatesTab.vue:42-70,158` | 本轮修复 R4-F3 |

### 中

| 编号 | 问题 | 位置 | 处置 |
|---|---|---|---|
| F-M1 | **ReportHeader「今天」呼吸圈在本周周日当天消失**（R3-F11 修复引入的边界回归）：今天=所展示周周日时 `elapsed=7`，pips 的 today 条件要求 `elapsed<7` → 当天 7 格全实心无 today 标记；「整周已过去」与「本周最后一天」两种 elapsed=7 未区分 | `views/weekly-report/components/ReportHeader.vue:99-114` | 本轮修复 R4-F4 |
| F-M2 | **`useScheduleActions.copyText` 绕过 `utils/clipboard.copyText`**：直接 `navigator.clipboard.writeText`，非 HTTPS/权限被拒时 undefined 直接抛错走「复制失败」；全库统一封装（textarea 降级+假成功防护）已被 borrow-flow/report 接入。且手写借用文案与 `views/borrow-flow/format.ts` 职责重复 | `views/panorama/useScheduleActions.ts:378-393` | 本轮修复 R4-F5 |
| F-M3 | **s2/s5 布局 dayTitle 用 dayjs `ddd` 但全项目从未加载 zh-cn locale → 中英混排**（"2026年10月15日 Thu"）；星期文案唯一来源纪律在 `utils/week.ts` | `views/panorama/layouts/s2-gantt/index.vue:167`、`s5-timeline/index.vue:135` | 本轮修复 R4-F6 |
| F-M4 | **抢占记录 `created_at` 三处裸展示后端原始串**（含 "T" 分隔符）：logs/borrow-flow 页均已统一 formatTime，这三处漏网 | `views/slot-config/components/RecordsPanel.vue:112`、`views/slot-booking/components/MyBookingsDrawer.vue:30`、`SlotDetailDialog.vue:35` | 本轮修复 R4-F7 |
| F-M5 | **`useScheduleData` 本地重复声明 `WEEKDAY_CN_MON`**：`utils/week.ts` 已导出逐字相同数组（s3-month/slot-config/TemplateDialog 均正确 import），此处复制一份并配 `(day()+6)%7` 下标换算——R3-F4「唯一来源」纪律漏网 | `views/panorama/useScheduleData.ts:77-85` | 本轮修复 R4-F6 |
| F-M6 | **权限判定与时长计算重复实现**：① `strategySource.permissionsOf` 手写 `admin || (pm && bound_version_id===versionId)`，与 `utils/business.canEditPanorama`（有单测、注释明言与后端对齐）完全同构未调用；② `slotSource` 私有 `durationOf` 与 `strategySource` 导出 `durationOf` 逐字重复 | `views/panorama/sources/strategySource.ts:43-60,114-121`、`sources/slotSource.ts:95-103` | 本轮修复 R4-F8 |
| F-M7 | **四个全景布局重复同组查询处理器**：`onVersionChange/onBranchChange/onScopeChange` 在五份文件逐字相同；`goThisWeek` 的周一计算在 s1/s4 内联重复且 `useScheduleData` 已有私有 `weekMondayOf` | `layouts/s1~s5 各 index.vue`、`useScheduleData.ts:58-62` | 本轮收敛进 usePanoramaPage R4-F9 |
| F-M8 | **`eventActions.ts` 纯函数零单测**：权限位→操作清单纯映射（S4/S5 共用、顺序即展示优先级），panorama 域其余纯函数模块均有 spec，唯独它没有 | `views/panorama/shared/eventActions.ts:16-97` | 本轮补测 R4-F10 |
| F-M9 | **抢占改期弹窗「确定改期」缺 `:loading`/在途守卫**：双击并发两个 PATCH（第二个大概率 40904 弹「目标时段被占」误导用户）；同弹窗组 BookingDialog/StrategyEditDialog 均有守卫 | `views/panorama/shared/ScheduleDialogs.vue:80-85`、`useScheduleActions.ts:186-206` | 本轮修复 R4-F11 |

### 低

| 编号 | 问题 | 处置 |
|---|---|---|
| F-L1 | `http.ts:92` 401 跳转手拼 `${pathname}#/login`，未走 `appHashUrl`（既定唯一来源，borrowFlowUrl 已接入） | 本轮修复 R4-F12 |
| F-L2 | 死代码/死导出（「为死代码维护测试」反模式复现）：`selectors.groupByBranch` 生产零调用而 s2-gantt 内联重新实现同一分组；`borrowSource.countPendingApproval` 生产零调用；`BorrowApprovalDrawer` 声明 `handled` 事件从未 emit | 本轮处置 R4-F13：groupByBranch 接线 s2 或删除、countPendingApproval 删除、handled 事件接线或删除 |
| F-L3 | `useScheduleData` 的 `autoRefreshMs` 死配置面且语义不自洽：唯一调用方从不传；传 false 时 visibilitychange 恢复仍会 pollOnce 一次 | 本轮修复 R4-F13（删选项或补守卫） |
| F-L4 | `DEFAULT_HORIZON_DAYS = 60` 双份（useScheduleData 与 slot-booking/index.vue 各一份，注释互相引用「口径一致」） | 本轮提常量单一来源 R4-F13 |
| F-L5 | 手拼日期/URL：`horizonEndOf` 用 `new Date()+setDate+padStart`（全库其余 40+ 处均 dayjs）；s1/s3 用模板串拼 `/panorama/timeline?date=` 而非 `router.push({path,query})` | 本轮修复 R4-F13 |
| F-L6 | 残留 any：`http.ts` 两拦截器 `(res: any)/(err: any)`；login `:type="group.color as any"`；report/detail `conclusionIconMap: Record<string, any>` | 本轮修复 R4-F14 |
| F-L7 | `monthsOf` 静默截断 3 个月：自定义范围超 3 个自然月时第 4 个月起抢占矩阵静默缺失，画布无提示（用户误读为「无抢占」） | 本轮加提示 R4-F13 |
| F-L8 | borrow-flow 状态筛选缺 `cancelled` 选项（撤销功能上线后漏配，撤销过的申请无法筛选定位） | 本轮修复 R4-F13 |
| F-L9 | StrategyEditDialog 模板列表降级后永不重试：首次 getTemplates 失败降级为单选项后数组非空，后续每次打开被锁死且无提示 | 本轮修复 R4-F13 |

**安全面**：panorama 域无 v-html/dangerouslyUseHTMLString（复制走 VNode 文本）；新端点均过 `authed_user` + 角色校验；未发现新增安全漏洞（B4-07/B4-18 为审计与限流硬化项，非直接漏洞）。

### 前端测试覆盖缺口

1. ★ `eventActions.ts` 全模块零测试（F-M8）：各权限位组合、动作顺序、withCopyAction 仅 borrow 追加
2. ★ `useScheduleActions` 动作总线零测试：batchRelease 他人条目 reason 收集（F-H2 修复后）、strategyCache 失效/版本切换（F-H1 修复后）、copyText 降级
3. ★ `ReportHeader` elapsed 0/7 边界与「今天=周日」场景（F-M1 修复回归锁定）
4. `selectors.groupByBranch` 若保留需接线后补语义测试；若删除则同步删 spec（F-L2）
5. `sources/strategySource.permissionsOf` 改用 canEditPanorama 后，既有 sources.spec 断言需对齐
6. `utils/week.weekMondayOf`（从 useScheduleData 抽出后）单测
7. borrow-flow 列表 cancelled 筛选项存在性（F-L8，constants 已有映射，补筛选选项断言）

**结构性说明**：第三轮之后 panorama 工作已建立组件级测试基建（vitest.setup.ts + @vue/test-utils，五布局均有组件 spec），本轮组件层修复（F-H3/F-M9/F-L9）可直接挂载测试或按既有「抽纯函数」路径锁定。

---

## 三、其他观察

- `backend/uv.lock` 未跟踪：仓库依赖声明在 `backend/pyproject.toml`（无 requirements.txt），uv.lock 是本地 uv 运行产物。**本轮处置**：加入根 `.gitignore` 并注明理由（依赖唯一来源为 pyproject.toml；若团队正式采用 uv 工作流可改为入库，勿长期悬置未跟踪）。
- 第三轮报告「记录在案」项复查：令牌吊销（改密不吊销存量 token）、settings 生产就绪残留（ALLOWED_HOSTS 默认 `*` 等）、getPlan 被 6 页当字典用、`today` setup 一次性求值跨零点漂移——均维持记录在案状态，本轮不重复展开。

## 四、评分与轨迹

| 轮次 | 后端 | 前端 | 说明 |
|---|---|---|---|
| 第一轮 2026-10-11 | ~5.5 | ~5.0 | 契约混乱、并发缺陷、生产阻断项成片 |
| 第二轮 2026-10-12 | ~7.0 | ~6.5 | 范式建立，主路径修复扎实 |
| 第三轮 2026-10-13 | ~7.5 | ~7.5 | 范式漏网路径 + 时区契约缺陷 + 组件层测试盲区 |
| **第四轮 2026-10-15** | **~7.5** | **~7.5** | 存量稳定，新增 panorama 域与三个新端点未过质量闸 |

**简评**：本轮问题不是范式退化，而是**新功能开发绕过了既有范式**——第三轮之后约 9100 行新代码（调度全景五布局 + 后端聚合端点）在没有质量审查的情况下合入，把「缓存失效、类型守卫、PROTECT 兜底、:loading 纪律、唯一来源」等已验证做法留在了存量代码里。第四轮优化（spec：`docs/superpowers/specs/2026-10-15-code-quality-optimization-round4-design.md`）以两条主线推进：**① 把范式补齐到全部新路径（panorama 域 + admin 侧 + 新端点）；② 字符串长度校验系统性补全（为 Postgres 迁移铺路）**，并建立「新功能合入前必须过质量清单」的纪律条目（写入 AGENTS.md）。
