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
| 电子流页面 | 独立一级菜单「借用审批」（`/borrow-flow/index`，rank 14，全角色可见），与全景页不绑定 |
| 审批权限 | admin 全部；pm 仅来源版本 = 自己绑定版本的电子流（前端隐藏按钮 + 服务端 `_can_approve` 双重校验） |
| 通过的落地动作 | 在目标分支按新时间创建策略，命名 `{原策略名}({目标版本}借用)`，沿用原模板、普通推送模式；经 `svc_create` 统一校验，冲突 → 40901/40902 且电子流保持待审批 |
| 防重复 | 同一策略同一借用人存在待审批申请时再次发起 → 40903 |
| 驳回 | 必填审批意见（前后端均校验） |
| 数据快照 | 电子流仅存 FK（strategy/borrower/target_branch），展示字段经 relation 实时读取；不冗余快照 |

## 3. 后端

- 模型 `BorrowFlow`（迁移 0011）：strategy / borrower / target_branch / new_build_time / reason / status(pending·approved·rejected) / approver / handle_comment / handled_at / created_at。
- API（`views/borrow_flow.py`）：
  - `GET /api/borrow-flows?status=` 列表：`status` 值域校验（pending/approved/rejected，非法 → 42201）；**按「与我相关」过滤（2026-10-12 补）**——admin 见全部，其余角色仅 `borrower=本人`，PM 追加来源版本 `pm_user=本人` 的电子流（避免他人版本的申请理由/审批意见对任意登录用户全量可见）；relation 实时组装名称；
  - `POST /api/borrow-flows` 发起（目标版本 ≠ 来源版本、时间格式 HH:MM、防重复待审批；另有 DB 层部分唯一约束 `uniq_pending_borrow_flow` 兜底并发双发起，IntegrityError → 40903）；
  - `POST /api/borrow-flows/<id>/approve` 通过（权限校验 → 事务内创建借用策略 + 乐观锁 `filter(status="pending").update()` 抢占，0 行更新 → 40903 重复处理）；
  - `POST /api/borrow-flows/<id>/reject` 驳回（必填意见）。
- seed 演示：pm26b 借用 27A-master-早间回归 至 26B/master@15:00（待审批，时段无冲突可供演示通过）；builder 的一条历史已驳回样例。

## 4. 前端

- `api/borrowFlow.ts`：类型 + 四个接口 + `formatBorrowFlowText`（复制文案纯函数，含单测）+ `borrowFlowUrl`（审批页直达链接 `…#/borrow-flow/index?focus=<id>`，2026-10-11 补）。
- `StrategyBorrowDialog.vue`：上半 el-descriptions 只读详情，下半借用表单；提交成功后引导「前往审批页」。
- `views/borrow-flow/index.vue`：状态筛选 + 「仅看我可审批的」 + 表格（策略/原时间/借用人/借用至/原因/状态/申请时间/审批）+ 操作列「复制 / 通过 / 驳回」（通过/驳回仅对 `canApprove` 行渲染）；复制走 `navigator.clipboard`，被拦截时降级为手动复制弹框（VNode 文本节点渲染，不用 `dangerouslyUseHTMLString`，杜绝他人输入 reason/审批意见的存储型 XSS，2026-10-12 加固）；**复制文案末尾附「审批详情链接」，页面加载时读取 `?focus=<id>` 自动定位并打开对应电子流详情（未找到则警告提示）**。
- 菜单：借用审批（`ep/tickets`，rank 14，ALL_ROLES）。

## 5. 测试

- 后端 `tests_borrow_flow.py` 12 例：发起校验（同版本目标 42201 / 重复待审批 40903 / 时间格式 42201 / 未认证 401）、审批权限（非来源 PM 40301、来源 PM 与 admin 通过）、通过即建策略（名称后缀/模板/审批人）、冲突保持待审批（40901/40902 且不落策略）、重复处理 40903、驳回必填意见、列表状态过滤。
- 前端 vitest：`formatBorrowFlowText` 3 例（待审批要素、已处理追加审批行、空原因占位）。
- 浏览器实测：builder 借用 → 提交成功跳转审批页（无审批按钮）→ pm27a 通过 → 26B 全景出现借用策略卡片 → 复制内容与剪贴板一致；冲突申请被正确拦截（40901，电子流保持待审批）。


## 修订记录（2026-10-12 第二轮质量优化）

- **列表可见性收敛为「与我相关」**：admin 全量；pm = 自己发起 + 自己审批（被借策略所属版本 PM）；其余角色 = 自己发起。此前任意登录用户可见全量电子流（含他人申请理由与审批意见）。
- **pending 唯一约束落 DB**：新增部分唯一约束 `uniq_pending_borrow_flow`（同策略 + 同借用人仅一条 pending，迁移 0012），并发重复发起由 IntegrityError → 40903 兜底，视图层预检查保留作友好路径。
- **状态参数值域校验**：`GET /borrow-flows?status=` 仅接受 pending/approved/rejected。
- **展示文案迁出 API 层**：状态文案唯一来源为 `frontend/src/views/constants.ts`（borrowStatusMeta），复制文案 `formatBorrowFlowText` 移至 `frontend/src/views/borrow-flow/format.ts`；复制降级弹框改用 VNode 文本渲染，消除 dangerouslyUseHTMLString 存储型 XSS。
