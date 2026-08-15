# 验证报告页面设计

日期：2026-08-15
状态：已确认

## 1. 背景与目标

构建策略配置系统（Vue3 + Element Plus + pure-admin-thin 前端，Django + SQLite 后端）新增「验证报告」功能模块。测试/构建人员完成某策略的验证后，填写结构化验证报告并发布；发布时自动截取报告页面截图随报告一起"推送"（本期为模拟推送），支持一键复制报告链接供外部快速查看。

目标：

1. 新增独立菜单「验证报告」：列表页 + 独立详情/编辑路由（方案 B）。
2. 报告为独立实体，填写时可选择关联版本与策略（可选关联）。
3. 支持新增、修改、发布、重新发布、查看全部历史报告、一键复制链接、快速直达指定报告。
4. 发布时前端自动截图（html2canvas）以 base64 上传后端存库，用于消息推送（模拟）。

## 2. 关键决策（已与用户确认）

| 决策点 | 结论 |
|--------|------|
| 页面结构 | 方案 B：列表页 `/report/index` + 独立详情/编辑路由 `/report/detail/:id`（`new` 表示新建），详情路由不出菜单（`showLink: false`） |
| 报告定位 | 独立实体，填写时可选关联版本/策略；不绑定执行轮次 |
| 内容形式 | 结构化表单（标题/结论/环境/验证内容/问题风险/备注） |
| 历史报告 | 全部报告的列表（含草稿与已发布） |
| 写权限 | tester/builder 可新建；修改/发布仅限报告作者本人；其余角色（admin/pm/integrator）只读 |
| 已发布行为 | 作者可继续编辑并「重新发布」，每次发布均重新截图+推送，产生新的发布记录 |
| 推送 | 前端截图调用后端真实接口上传；推送为模拟：后端收到后仅打印推送消息日志（摘要+截图信息），不调用真实推送服务；`push_status=pushed`、模拟接收人、推送摘要文本，架构预留真实对接扩展点 |
| 截图方案 | 前端 html2canvas 截取报告卡片 DOM（scale=2）→ PNG base64（≤2MB）→ JSON body 上传后端存入 SQLite |
| 深链接 | `{origin}/#/report/detail/{id}`，打开即直达指定报告；不存在的 id 提示并回列表 |
| 菜单位置 | 「验证报告」插入「策略配置」与「系统管理」之间（rank 7，原系统管理/日志中心顺延为 8/9） |

## 3. 数据模型

在 `build_protection_service/models.py` 新增两张表：

```
VerificationReport（验证报告）
├── title            CharField(200)         标题（必填）
├── version          FK(Version, null=True, blank=True)    可选关联
├── strategy         FK(Strategy, null=True, blank=True)   可选关联，须属于所选版本
├── conclusion       CharField(20)          结论 pass/fail/risk（必填）
├── environment      CharField(255)         验证环境（可空）
├── summary          TextField              验证内容（必填）
├── risks            TextField              问题与风险（可空）
├── remark           TextField              备注（可空）
├── status           CharField(20)          draft/published，默认 draft
├── created_by       FK(User, PROTECT)      作者
├── published_at     DateTimeField(null)    最近发布时刻
├── publish_count    PositiveIntegerField   发布次数，默认 0
├── created_at / updated_at

ReportPublishRecord（发布暨推送记录）
├── report           FK(VerificationReport, CASCADE)
├── publisher        FK(User, PROTECT)
├── screenshot       TextField              PNG base64（≤2MB）
├── push_status      CharField(20)          pushed/failed（模拟，本期恒 pushed）
├── push_target      CharField(100)         模拟接收人，如「构建通知群」
├── message          CharField(255)         模拟推送摘要文本
├── created_at
```

## 4. API 契约

挂载 `/api`，沿用统一响应 `{code, message, data}`；错误码沿用现有体系：`40101`/`40301`/`40401`/`42201`。

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/reports` | 列表，支持 `status`、`version_id`、`strategy_id`、`keyword`（匹配标题/ID）过滤，按 `-updated_at` 排 | 全员 |
| POST | `/reports` | 新建（默认 draft），返回完整报告 | tester/builder |
| GET | `/reports/<id>` | 详情 | 全员 |
| PUT | `/reports/<id>` | 修改内容（新建后未发布或已发布均可改） | 仅作者 |
| POST | `/reports/<id>/publish` | 发布：body `{ screenshot }`，校验必填与 ≤2MB；创建发布记录、状态转 published、更新 published_at/publish_count、模拟推送 | 仅作者 |
| GET | `/reports/<id>/publishes` | 该报告的全部发布记录（含截图 base64），按时间倒序 | 全员 |

### 4.1 权限矩阵

| 操作 | admin | pm | builder | tester | integrator |
|------|:---:|:---:|:---:|:---:|:---:|
| 列表/详情/发布历史/复制链接 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 新建 | ✗ | ✗ | ✓ | ✓ | ✗ |
| 修改 / 发布（作者） | ✗ | ✗ | ✓ | ✓ | ✗ |
| 修改 / 发布（非作者） | ✗ | ✗ | ✗ | ✗ | ✗ |

## 5. 前端设计

### 5.1 路由

在 `frontend/src/router/asyncRoutes.ts` 新增 `/report` 模块，菜单「验证报告」rank 7：

| 路由 | 名称 | 菜单 | 说明 |
|------|------|------|------|
| `/report/index` | ReportIndex | 可见 | 列表页 |
| `/report/detail/:id` | ReportDetail | 隐藏 | 详情/编辑共用；`:id = "new"` 表示新建 |

进入详细页后：
- 只读态：展示报告卡片 + 顶部「返回 / 复制链接 / 编辑（作者可见）/ 发布、重新发布（作者可见，草稿显示发布，已发布显示重新发布）」+ 底部「发布历史」（可展开，含各次截图缩略图，点击放大）。
- 编辑态：字段为表单控件（标题输入、版本/策略级联下拉、结论单选、多行文本域），按钮为「保存草稿 / 发布」。已发布报告编辑态按钮为「保存 / 重新发布」。

### 5.2 列表页 /report/index

- 顶部筛选：状态（全部/草稿/已发布）、版本、策略（级联于版本）、关键词搜索（标题/ID）
- 「＋ 新增报告」→ 跳 `/report/detail/new`（仅 tester/builder 显示）
- 表格列：ID、标题、关联策略、结论徽章、状态徽章、作者、更新时间、操作（查看 / 编辑[作者] / 复制链接），点击标题进详情
- 复制链接：复制 `{origin}/#/report/detail/{id}` 并提示成功

### 5.3 详情/编辑页 /report/detail/:id

- 报告卡片 = 截图区域（标题、结论徽章、版本/策略关联、作者/发布时间元信息、验证环境、验证内容、问题与风险、备注）
- 新建（:id=new）：直接进入编辑态，保存成功跳转至 `/report/detail/{id}`
- 深链接打开：id 存在则渲染，40401 提示并回列表

## 6. 发布流程（截图 + 推送）

1. **内容落地**：编辑态存在未保存修改时，先 `PUT /reports/<id>` 保存，等待返回再继续。
2. **截图**：html2canvas 对报告卡片 DOM 截图（scale=2、白底）→ PNG base64；前端校验 ≤2MB，超限报错终止。
3. **发布**：`POST /reports/<id>/publish`，body `{ screenshot: "data:image/png;base64,..." }`。
4. **后端**：校验作者与写角色 → 创建 `ReportPublishRecord`（screenshot、push_target=「构建通知群」、message=「报告《title》已发布，结论：xxx」、push_status=pushed）→ 报告 status=published、published_at、publish_count+1 → 打印模拟推送日志（含推送摘要文本与截图 base64 长度），**仅打印、不调用真实推送服务**。
5. **前端反馈**：「发布成功，已推送至构建通知群」，刷新详情展示最新发布历史。

截图失败（DOM 异常/页面未就绪）则中止发布并提示，不产生发布记录，保证"一次发布 = 一条记录"。

## 7. 错误处理

- `40101` 未认证 → 拦截器跳登录
- `40301` 非写角色 / 非作者 → 拦截器提示「无权限执行该操作」
- `42201` 必填缺失、结论非法、截图超 2MB → 提示后端 message
- `40401` 报告不存在 → 提示并返回列表（含深链接直达场景）

## 8. 依赖变更

前端新增 `html2canvas`（截图库，当前无此依赖）。

## 9. 测试计划

**后端**（Django tests.py，沿用现有 pytest 风格）：
- 权限矩阵：tester/builder 可新建；admin/pm/integrator 新建 → 40301；非作者修改/发布 → 40301
- 校验：缺标题/结论/验证内容 → 42201；截图超 2MB → 42201
- 发布链路：首次发布生成一条记录、status/published_at/publish_count 正确；重新发布追加记录且 publish_count+1
- 列表过滤：status / version_id / strategy_id / keyword

**前端**：
- `npm run typecheck` 通过
- 浏览器手动联调：新建 → 保存草稿 → 编辑 → 发布（截图回显）→ 重新发布 → 复制链接 → 深链接直达；404 场景