# 日志分页协议设计（M-3）

> 日期：2026-10-11
> 来源：代码质量复评报告 `docs/code-quality-assessment-2026-10-11-review.md` 中危项 M-3
> 状态：待评审 → 评审通过后实施

## 1. 现状与问题

4 个日志端点全部为**硬截断** `qs.order_by("-id")[:200]`：

| 端点 | 模型 | 增长速度 | 截断后果 |
|---|---|---|---|
| `GET /logs/execution` | ExecutionLog | **快**（随构建持续写入，500 台机器规模下尤甚） | 早期日志永久不可见 |
| `GET /logs/changes` | StrategyChangeLog | 中 | 同上 |
| `GET /admin/logs/operations` | AdminOpLog | 中 | 同上 |
| `GET /admin/logs/security` | SecurityLog | 中（含登录成功/失败/锁定，溯源价值高） | 同上 |

前端 `views/logs/index.vue` 四个 tab 各一张表一次性渲染全部数据，无分页组件；`api/logs.ts` 返回类型为裸数组。

另：`executions.py round_detail` 的轮次日志 `r.logs.all()` 为全量返回 —— 单轮次日志量级为几十条，**不纳入本次分页**，仅加 500 条防御上限并注释原因（嵌套结构、详情面板一次性渲染，分页破坏阅读连续性）。

## 2. 协议

### 请求（新增两个可选 query 参数）

```
page       int  页码，从 1 开始，默认 1；非正整数/非数字 → 42201
page_size  int  每页条数，默认 50，上限 200（超出按 200，不报错——宽容处理防误用）
```

### 响应（`data` 由数组变为对象，破坏性变更）

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [ ... ],      // 当前页数据，序列化结构不变
    "total": 183,          // 当前过滤条件下的总条数（一次 COUNT）
    "page": 1,
    "page_size": 50
  }
}
```

`has_more` 不单独提供，前端由 `page * page_size < total` 推导。

### 兼容性决策

**不做双模式**。理由：前后端同仓库，前端 4 处调用与后端在同一次提交内同步切换；保留「裸数组/分页对象」双模式会让契约文档与测试双份，长期成本高于一次性切换的迁移成本。切换提交内同步更新 `LogsEndpointsTests` 既有断言。

## 3. 后端实现

### 统一助手（views/__init__.py）

```python
def paginate(request, qs, serializer, *, default_page_size=50, max_page_size=200):
    """对 QuerySet 分页并统一序列化，返回 ok({...}) 响应。

    - page 非法（非数字/<=0）→ 42201；
    - page_size 超上限按上限截断（不报错）；
    - serializer: 单条记录的 dict 化函数；
    - 返回的 QuerySet 已按传入顺序切片，调用方无需再关心切片。
    """
    page = parse_int(request.GET.get("page"), ) or 1  # 实现时以 parse_int 兜底
    ...
```

> 实施注意：`parse_int` 已存在（ID 防护批次落地），`page` 校验复用它；`page_size` 同理。
> 越界页（page 超过总页数）返回空 `items` + 真实 `total`，由前端分页组件自然处理，不报错。

### 端点改造（4 处各缩为 1~2 行）

- `views/logs.py` execution_logs / change_logs：现有 select_related / order_by / 过滤逻辑全部保留，切片替换为 `paginate(request, qs, serializer)`；
- `views/admin.py` logs_view：operations / security 两分支同款；
- 顺带修复既有不一致：`logs_view` 的 `created_at` 直出 datetime 对象，而 `logs.py` 走 `fmt_dt`——本次统一为 `fmt_dt`（前端展示本就按字符串处理，无破坏）。

## 4. 前端实现

### 类型（api/types.ts）

```ts
export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
```

### API（api/logs.ts）

4 个方法返回类型 `Promise<T[]>` → `Promise<Paged<T>>`，参数增加 `page?: number; page_size?: number`。

### 页面（views/logs/index.vue）

- 每个 tab 一组状态：`execPage = ref(1)`、`execTotal = ref(0)`（4 组）；
- load 函数传入 `page`/`page_size`，响应解构 `items`/`total`；
- 表格下方加 `el-pagination`（`layout="total, prev, pager, next"`，`page-size` 50）；
- 切 tab 时重置该 tab 页码为 1（`onTabChange` 已有分发点）；
- 筛选条件变化（日期/版本/分支/时间范围）同样重置页码 —— **筛选变更不清零页码会看到空页**，是分页改造最常见的回归点，测试必须覆盖。

## 5. 测试

后端新增 `tests_log_pagination.py`：

1. 默认参数：不传 page/page_size → page=1、page_size=50、total 正确、items ≤ 50；
2. 翻页：造 60 条，page=2 返回剩余 10 条且 total=60；
3. page_size 上限：传 999 → 返回 200 条（按上限截断）；
4. 非法 page：`page=0`/`page=abc` → 42201；
5. 过滤组合：date/version_id 过滤与分页共存，total 为过滤后计数；
6. PM 权限不受影响：PM 仍只见本版本日志；
7. 既有 `LogsEndpointsTests`：断言 `resp.json()["data"]` 改为 `["data"]["items"]`。

前端：现有 46 例无断言日志结构，不破坏；logs 页分页为视图逻辑，暂不加组件测试（与项目现状一致，交互逻辑薄）。

## 6. 改动清单与规模

| 文件 | 改动 |
|---|---|
| `views/__init__.py` | +paginate 助手（约 25 行） |
| `views/logs.py` | 2 端点改写（各 -5 +3 行） |
| `views/admin.py` | logs_view 改写（-18 +8 行） |
| `views/executions.py` | round_detail logs 加 500 上限（1 行） |
| `api/types.ts` | +Paged<T>（5 行） |
| `api/logs.ts` | 4 方法签名与泛型（约 12 行） |
| `views/logs/index.vue` | 4 tab 分页状态 + el-pagination（约 60 行） |
| `tests_log_pagination.py` | 新增约 7 例 |
| `tests.py` | LogsEndpointsTests 断言适配（约 6 处） |

预计后端测试 183 → 190 例。

## 7. 不做的事

- 不引入 DRF Paginator/DRF 分页类（项目为纯函数视图，自定义助手更贴合现有 `ok()` 契约）；
- 不做游标分页/无限滚动（管理后台表格场景，页码分页足矣）；
- round_detail 轮次日志不做真分页（见第 1 节）；
- 不改 `SecurityLog`/`AdminOpLog` 的模型结构。
