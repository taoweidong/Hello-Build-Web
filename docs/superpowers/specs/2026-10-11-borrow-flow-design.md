# 借用电子流（借用审批）设计

日期：2026-10-11
状态：已确认

## 1. 背景与目标

版本策略全景(New)页面对外部人员只读。非当前版本的人员（其他版本 PM、构建/测试/集成人员）如需复用某策略的构建时间，此前无任何途径。新增**借用电子流**：

- 无修改权限的用户点击策略卡片 → 只读查看策略详情 → **发起借用申请**（借用至自己的版本/分支 + 新构建时间）；
- 申请生成电子流，由**被借用策略所属版本的负责人（PM）或 admin** 在独立的「借用审批」页面审批；
- **审批通过 = 立即在目标分支按新时间实际创建借用策略**（复用策略共用写路径，统一互斥/阶段冲突校验；冲突则电子流保持待审批）；
- 审批页支持**一键复制**电子流内容为纯文本，方便粘贴发给审核人员。

## 2. 关键决策

| 决策点 | 结论 |
|--------|------|
| 入口 | 版本策略全景页卡片点击：有编辑权限 → 既有编辑弹窗；无权限 → 新的「策略详情与借用申请」弹窗 |
| 借用表单 | 目标版本（排除当前版本，PM 默认选绑定版本）/ 目标分支（甘特聚合接口按版本取分支）/ 新构建时间（默认沿用原时间）/ 借用原因 |
| 电子流页面 | ~~独立一级菜单「借用审批」（`/borrow-flow/index`，rank 14，全角色可见）~~——2026-10-20 页面精简已删除独立页，入口收敛在调度全景「待我审批」红点 + 审批抽屉（见修订六） |
| 审批权限 | admin 全部；pm 仅来源版本 = 自己绑定版本的电子流；**自借自批回避（2026-10-18 定案）：借用人不可审批（通过/驳回）自己发起的电子流，admin 亦不例外（→ 40301），撤回出口走 cancel**（前端隐藏按钮 + 服务端 `_can_approve` 双重校验） |
| 通过的落地动作 | 在目标分支按新时间创建策略，命名 `{原策略名}({目标版本}借用)`，沿用原模板与推送配置（`push_mode`/`push_start_time` 从源策略复制，2026-10-13 修订——此前固定普通推送模式且丢弃推送时间）；经 `svc_create` 统一校验，冲突 → 40901/40902 且电子流保持待审批 |
| 防重复 | 同一策略同一借用人存在待审批申请时再次发起 → 40903 |
| 驳回 | 必填审批意见（前后端均校验） |
| 数据快照 | 电子流仅存 FK（strategy/borrower/target_branch），展示字段经 relation 实时读取；不冗余快照 |

## 3. 后端

- 模型 `BorrowFlow`（迁移 0011）：strategy / borrower / target_branch / new_build_time / reason / status(pending·approved·rejected·cancelled，cancelled 与 cancelled_at 为 2026-10-13 撤销功能新增，迁移 0013) / approver / handle_comment / handled_at / created_at。
- API（`views/borrow_flow.py`）：
  - `GET /api/borrow-flows?status=` 列表：`status` 值域校验（pending/approved/rejected/cancelled，非法 → 42201；cancelled 随 2026-10-13 撤销功能纳入）；**按「与我相关」过滤（2026-10-12 补）**——admin 见全部，其余角色仅 `borrower=本人`，PM 追加来源版本 `pm_user=本人` 的电子流（避免他人版本的申请理由/审批意见对任意登录用户全量可见）；relation 实时组装名称；
  - `POST /api/borrow-flows` 发起（目标版本 ≠ 来源版本、时间格式 HH:MM、防重复待审批；另有 DB 层部分唯一约束 `uniq_pending_borrow_flow` 兜底并发双发起，IntegrityError → 40903）；
  - `POST /api/borrow-flows/<id>/approve` 通过（权限校验 → 事务内创建借用策略 + 乐观锁 `filter(status="pending").update()` 抢占，0 行更新 → 40903 重复处理）；
  - `POST /api/borrow-flows/<id>/reject` 驳回（必填意见）。
- seed 演示：pm26b 借用 27A-master-早间回归 至 26B/master@15:00（待审批，时段无冲突可供演示通过）；builder 的一条历史已驳回样例。

## 4. 前端

- `api/borrowFlow.ts`：类型 + 四个接口（2026-10-20 页面精简后仅服务全景域行内动作）；`formatBorrowFlowText` 复制文案纯函数（含单测）现居 `views/panorama/shared/borrowFormat.ts`；`borrowFlowUrl` 审批页直达链接（`…#/borrow-flow/index?focus=<id>`，2026-10-11 补）已随独立页下线删除。
- `StrategyBorrowDialog.vue`：上半 el-descriptions 只读详情，下半借用表单；提交成功后引导「前往审批页」。
- ~~`views/borrow-flow/index.vue`~~（独立审批页，2026-10-20 页面精简删除）：状态筛选 + 「仅看我可审批的」 + 表格（策略/原时间/借用人/借用至/原因/状态/申请时间/审批）+ 操作列「复制 / 通过 / 驳回」（通过/驳回仅对 `canApprove` 行渲染）；复制走 `navigator.clipboard`，被拦截时降级为手动复制弹框（VNode 文本节点渲染，不用 `dangerouslyUseHTMLString`，杜绝他人输入 reason/审批意见的存储型 XSS，2026-10-12 加固）；复制文案末尾附「审批详情链接」，页面加载时读取 `?focus=<id>` 自动定位——上述交互由全景域审批抽屉与行内动作承接，`?focus=<id>` 深链定位随页面成为历史。
- ~~菜单：借用审批（`ep/tickets`，rank 14，ALL_ROLES）~~（2026-10-20 页面精简移除）。

## 5. 测试

- 后端 `tests_borrow_flow.py` 12 例：发起校验（同版本目标 42201 / 重复待审批 40903 / 时间格式 42201 / 未认证 401）、审批权限（非来源 PM 40301、来源 PM 与 admin 通过）、通过即建策略（名称后缀/模板/审批人）、冲突保持待审批（40901/40902 且不落策略）、重复处理 40903、驳回必填意见、列表状态过滤。
- 前端 vitest：`formatBorrowFlowText` 3 例（待审批要素、已处理追加审批行、空原因占位）。
- 浏览器实测：builder 借用 → 提交成功跳转审批页（无审批按钮）→ pm27a 通过 → 26B 全景出现借用策略卡片 → 复制内容与剪贴板一致；冲突申请被正确拦截（40901，电子流保持待审批）。


## 修订记录（2026-10-12 第二轮质量优化）

- **列表可见性收敛为「与我相关」**：admin 全量；pm = 自己发起 + 自己审批（被借策略所属版本 PM）；其余角色 = 自己发起。此前任意登录用户可见全量电子流（含他人申请理由与审批意见）。
- **pending 唯一约束落 DB**：新增部分唯一约束 `uniq_pending_borrow_flow`（同策略 + 同借用人仅一条 pending，迁移 0012），并发重复发起由 IntegrityError → 40903 兜底，视图层预检查保留作友好路径。
- **状态参数值域校验**：`GET /borrow-flows?status=` 仅接受 pending/approved/rejected。
- **展示文案迁出 API 层**：状态文案唯一来源为 `frontend/src/views/constants.ts`（borrowStatusMeta），复制文案 `formatBorrowFlowText` 移至 `frontend/src/views/borrow-flow/format.ts`；复制降级弹框改用 VNode 文本渲染，消除 dangerouslyUseHTMLString 存储型 XSS。

## 修订记录（2026-10-13 第三轮质量优化）

- **审批通过保留推送配置（R3-B15）**：通过建新策略时 `push_mode`/`push_start_time` 从源策略复制——此前固定 `push_mode="normal"` 且丢弃 `push_start_time`，sync/固定推送策略被借用后推送配置丢失。
- **方法守卫（R3-B16）**：`approve`/`reject` 仅允许 POST（此前 GET 也会执行审批产生副作用）；列表端点非 GET/POST → 42201（此前 DELETE/PUT 被当列表请求执行）。
- **请求体类型守卫（R3-B2）**：`new_build_time`/`reason`/`comment` 非字符串一律经 `body_str` 归一为 `""` 走既有校验分支（42201），此前在 `.strip()` 处冒 AttributeError 变 500。
- **时间序列化统一上海墙钟（R3-B3）**：`handled_at`/`created_at` 走 `fmt_dt`（此前手工 strftime 输出 UTC 墙钟，前端早 8 小时展示）。
- **联动变更**：策略删除前拦截 pending 借用流（40903，防 `BorrowFlow.strategy` CASCADE 静默抹掉进行中电子流，见 build-strategy-web spec 同日修订）；前端时间格式化统一 `formatFlowTime`（内部走 `utils/business.formatTime`，输出与手写 `.replace("T"," ")` 逐字节等价）；`borrowFlowUrl` 改用 `utils/appUrl.appHashUrl` 拼装；`formatBorrowFlowText` 补 approved 分支与 approver_name/handle_comment/handled_at 空值兜底测试（`api/__tests__/borrowFlow.spec.ts`）。

## 修订记录（2026-10-15 第四轮质量优化，并回填 2026-10-13 撤销功能）

- **撤销功能回填（2026-10-13 随调度全景 P2 上线，此前仅记于调度全景 spec 修订五）**：新增 `POST /api/borrow-flows/<id>/cancel`——仅借用人本人、仅 pending 可撤，条件 UPDATE `filter(id, status="pending").update(...)` 防并发双撤；`BorrowFlow` 增 `cancelled` 状态与 `cancelled_at` 字段（migration 0013）；撤销不删记录保留审计；`uniq_pending_borrow_flow` 只约束 pending，撤销后同策略可立即重发。前端状态筛选补 cancelled 选项（此前撤销过的申请无法筛选定位，R4-F13）；调度全景 S1/S4/S5 与审批抽屉提供撤销入口（权限位 `canCancel`，见调度全景 spec 修订五/六）。
- **列表可选分页（R4-B13）**：携带 `page` 参数返回 `{items,total,page,page_size}`（走 `views/__init__.paginate_qs`，page_size 默认 20 上限 100），不携带保持全量数组——与 reports 列表向后兼容口径一致，前端未改造前行为不变。
- **单条响应路径 select_related（R4-B14）**：`_payload` 所需关联清单抽公共 `_flow_qs()`，create/approve/reject/cancel 单条响应与列表路径复用——此前单条路径逐关联点查固定 N+1（6+ 次查询，`assertNumQueries` 锁定）；approve 原 `refresh_from_db` 改为 `_flow_qs` 重取，同时消除 approver 关联缓存陈旧问题。
- **长度守卫（R4-B10）**：审批通过建策略拼接名 `{原策略名}({目标版本}借用)` 防御性截断到 `Strategy.name` 上限 200（源策略名 ≤200 + 版本名 + 后缀可超限，SQLite 放行、迁 Postgres 即 DataError 500）；发起 `reason` 超 500、审批意见 `comment` 超 255 截断（审计/备注类字段沿用 `body_str` max_len 截断口径）。（2026-10-24 R6-B7 起 `reason` 超 500 改 `check_str_len` 42201 **拒绝**——拒绝优于截断，见修订六；`comment` 仍为截断口径。）
- **策略删除拦截收敛（R4-B1）**：第三轮的「删除策略前拦截 pending 借用流（40903）」仅 PM 入口生效，admin 入口 `_delete_admin_strategy` 直接 `s.delete()` 会经 CASCADE 静默抹掉进行中电子流（admin 反而约束更松）。现拦截 + 删除收敛到共享 `services.strategies.delete_strategy`（同一事务），PM 与 admin 两入口行为一致；审计仍由调用方入口写 AdminOpLog（R3-B5 口径不变）。

## 修订记录（2026-10-18 第五轮质量优化）

- **自借自批回避（R5-B10，决策定案）**：`_can_approve` 增加 `flow.borrower_id != user.id`——**禁止审批自己发起的借用申请，admin 亦不例外**（对照 cancel 端点「仅本人」的既有审计取向；电子流的核心价值即审批留痕的独立性，自借自批在审计报表中无法与正常审批区分）。approve/reject 自己的电子流 → 40301「不可审批自己发起的借用申请」；借用人想撤回申请应走 `POST /borrow-flows/<id>/cancel`（撤销不受回避规则影响）。回归测试 `tests_quality_round5.py::BorrowSelfApprovalTests`。
- **前端复制文案 cancelled 三态分支（R5-F2）**：`views/borrow-flow/format.ts formatBorrowFlowText` 非 pending 态由「approved/其余一律按驳回拼审批人」改为 approved/rejected/cancelled 三态分支——cancelled 拼「撤销：借用人撤销于 {cancelled_at}」，不再误拼审批人与意见（此前已撤销的申请复制出来显示为「驳回」）。
- **正文回填**：§2 审批权限行补自借自批回避；§3 模型 status 枚举与列表 `status` 值域补 `cancelled`（该值域实际自 2026-10-13 撤销功能上线即含 cancelled，此前正文只记了三态、修订四仅记了前端筛选项）。

## 修订记录（2026-10-20 页面精简 + 2026-10-24 第六轮质量优化）

- **独立审批页与深链删除（2026-10-20 页面精简，commit b37bab6）**：`/borrow-flow/index` 独立页、菜单项与 `borrowFlowUrl` 直达链接删除，入口收敛为调度全景「待我审批」红点 + 审批抽屉；`views/borrow-flow/format.ts` 迁 `views/panorama/shared/borrowFormat.ts`（`formatFlowTime` 别名随之）；§2/§4 中独立页与菜单描述转为历史记录。
- **发起 reason 超长改拒绝（R6-B7）**：`views/borrow_flow.py` 发起借用的 `reason` 由 `body_str(max_len=500)` 截断改为 `check_str_len` 42201 拒绝（reason 是审批人决策的核心内容，拒绝优于静默截断）；审批意见 `comment` 属审计备注类，维持 255 截断口径。回归 `tests_quality_round6.py`。
- **borrower 外键改 PROTECT（R6-B6，migration 0016）**：`BorrowFlow.borrower` 由 CASCADE 改 PROTECT，删除借用人被数据库层拦截（`ProtectedError`）——pending 单是审批人待办、approved 单是执行凭证，审计链发起方必须强存活，与 `approver` 及审计表 `operator` 口径对齐。回归 `tests_quality_round6.py::BorrowerProtectTests`。
- **panorama 待办排除自借单（R6-B8）**：`GET /api/panorama/todos` 的 `pending_approval` 在角色过滤前先 `.exclude(borrower=user)`——R5-B10 回避规则下本人发起的申请自己永远不可审批，计入待办只会产生不可操作的假待办。
