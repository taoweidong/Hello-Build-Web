# 验证报告页面实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增验证报告页面：填写/修改/发布/查看历史报告，一键复制链接与深链接快速查看，发布时自动截图上传后端，后端模拟推送（仅打印日志）。

**Architecture:** 后端新增 `VerificationReport`（报告实体）与 `ReportPublishRecord`（发布暨推送记录）两表；6 个 API（列表/新建/详情/修改/发布/发布历史），写角色为 tester/builder、修改发布仅限作者；发布时前端 html2canvas 截取报告卡片 PNG base64 上传，后端落库并打印模拟推送日志。前端新增列表页 `/report/index` 与详情/编辑页 `/report/detail/:id`（`:id="new"` 新建，`showLink:false` 不出菜单）。

**Tech Stack:** Django 5 + SQLite + unittest/APIClient；Vue3 `<script setup>` + Element Plus + TypeScript + html2canvas。

**契约基准:** `docs/superpowers/specs/2026-08-15-verification-report-design.md`（commit `e9def92`）

---

## 文件结构

| 文件 | 责任 |
|---|---|
| Modify: `backend/build_protection_service/models.py` | 追加 `VerificationReport`、`ReportPublishRecord` 两个模型 |
| Create: `backend/build_protection_service/views/reports.py` | 报告 4 个视图函数（列表/详情/发布/发布历史） |
| Modify: `backend/build_protection_service/views/urls.py` | 注册 4 条 reports 路由 |
| Modify: `backend/build_protection_service/tests.py` | 追加 `ReportApiTests`（TDD 红先行） |
| Modify: `frontend/src/api/types.ts` | 追加 `ReportItem`、`ReportPublishItem` 类型 |
| Create: `frontend/src/api/report.ts` | 报告 API 模块 + `ReportForm`/`ReportQuery` |
| Create: `frontend/src/views/report/index.vue` | 报告列表页（筛选/表格/复制链接/新增） |
| Create: `frontend/src/views/report/detail.vue` | 报告详情/编辑页（截图发布/发布历史回显） |
| Modify: `frontend/src/router/asyncRoutes.ts` | 插入 `/report` 模块（rank 7），system/logs 顺延 |
| Modify: `frontend/package.json` | `pnpm add html2canvas` 自动追加依赖 |

**测试与联调环境:** 种子用户 `tester`/`builder`（密码 `123456`）已存在（`seed.py`）；后端 `python manage.py runserver 8000`、前端 `pnpm dev` 端口 `8848`（`VITE_API_BASE_URL=http://localhost:8000/api`，hash 路由）。

---

### Task 1: 数据模型与迁移

**Files:**
- Modify: `backend/build_protection_service/models.py`（文件末尾追加）

- [x] **Step 1: 追加两个模型**

在 `models.py` 末尾（`SecurityLog` 之后）追加以下代码（复用文件顶部已定义的 `User`、`Version`、`Strategy`）：

```python
class VerificationReport(models.Model):
    """验证报告：独立实体，可选关联版本/策略。"""
    CONCLUSION_CHOICES = (("pass", "通过"), ("fail", "不通过"), ("risk", "有风险"))
    STATUS_CHOICES = (("draft", "草稿"), ("published", "已发布"))
    title = models.CharField("标题", max_length=200)
    version = models.ForeignKey(Version, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    strategy = models.ForeignKey(Strategy, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    conclusion = models.CharField("结论", max_length=20, choices=CONCLUSION_CHOICES)
    environment = models.CharField("验证环境", max_length=255, blank=True, default="")
    summary = models.TextField("验证内容")
    risks = models.TextField("问题与风险", blank=True, default="")
    remark = models.TextField("备注", blank=True, default="")
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default="draft")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_reports")
    published_at = models.DateTimeField(null=True, blank=True)
    publish_count = models.PositiveIntegerField("发布次数", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class ReportPublishRecord(models.Model):
    """发布暨推送记录：每次发布追加一条，含截图与模拟推送摘要。"""
    report = models.ForeignKey(VerificationReport, on_delete=models.CASCADE, related_name="publish_records")
    publisher = models.ForeignKey(User, on_delete=models.PROTECT, related_name="report_publishes")
    screenshot = models.TextField("页面截图 base64")
    push_status = models.CharField("推送状态", max_length=20, default="pushed")
    push_target = models.CharField("模拟接收人", max_length=100, default="构建通知群")
    message = models.CharField("推送摘要", max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.report.title} 发布于 {self.created_at:%m-%d %H:%M}"
```

- [x] **Step 2: 生成并应用迁移**

```bash
cd backend
python manage.py makemigrations build_protection_service
python manage.py migrate
```

Expected: 生成 `0002_verificationreport_reportpublishrecord.py`，migrate 无错误输出。

- [x] **Step 3: 回归现有测试**

```bash
python manage.py test build_protection_service -v 1
```

Expected: 全部 PASS（既有 SeedTests/StrategyApiTests 等不回退）。

- [x] **Step 4: Commit**

```bash
git add backend/build_protection_service/models.py backend/build_protection_service/migrations/0002_verificationreport_reportpublishrecord.py
git commit -m "feat: 新增验证报告与发布记录模型"
```

---

### Task 2: API 测试先行（TDD 红）

**Files:**
- Modify: `backend/build_protection_service/tests.py`（文件末尾追加 `ReportApiTests`）

- [x] **Step 1: 追加完整测试类**

在 `tests.py` 末尾追加（无需改 import，模型已由文件顶部导入）：

```python
class ReportApiTests(ConfigAwareTestCase):
    """验证报告 API：tester/builder 可写，仅作者可改/发，发布为模拟推送。"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.pm = User.objects.create_user(username="pm1", password="123456", role="pm")
        self.admin = User.objects.create_user(username="admin", password="123456", role="admin")
        self.tester = User.objects.create_user(username="tester1", password="123456", role="tester")
        self.tester2 = User.objects.create_user(username="tester2", password="123456", role="tester")
        self.builder = User.objects.create_user(username="builder1", password="123456", role="builder")
        self.integrator = User.objects.create_user(username="intg1", password="123456", role="integrator")
        self.version = Version.objects.create(name="27A", pm_user=self.pm, status="active")
        self.branch = Branch.objects.create(version=self.version, name="master")
        self.tmpl = StrategyTemplate.objects.create(name="晚间全量冒烟", smoke_minutes=480, analysis_minutes=120)
        self.strategy = Strategy.objects.create(
            branch=self.branch, template=self.tmpl, name="27A-master-晚间",
            build_start_time="22:00", push_mode="normal", created_by=self.pm,
        )
        self.token = self._login("tester1")

    def _login(self, username):
        resp = self.client.post("/api/auth/login", {"username": username, "password": "123456"}, format="json")
        return resp.json()["data"]["token"]

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _valid(self, **overrides):
        payload = {
            "title": "27A 冒烟验证报告",
            "version_id": self.version.id,
            "strategy_id": self.strategy.id,
            "conclusion": "pass",
            "environment": "测试环境",
            "summary": "冒烟用例全部通过，无阻塞问题。",
            "risks": "",
            "remark": "",
        }
        payload.update(overrides)
        return payload

    def test_writer_roles_can_create_report(self):
        # tester 与 builder 均可新建（草稿态）
        self._auth(self.token)
        resp = self.client.post("/api/reports", self._valid(), format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["conclusion"], "pass")
        self.assertEqual(data["version_name"], "27A")
        self.assertEqual(data["strategy_name"], "27A-master-晚间")
        self.assertEqual(data["created_by_id"], self.tester.id)
        self._auth(self._login("builder1"))
        resp = self.client.post("/api/reports", self._valid(title="builder 报告"), format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["title"], "builder 报告")

    def test_non_writer_cannot_create_report(self):
        for username in ("pm1", "admin", "intg1"):
            self._auth(self._login(username))
            resp = self.client.post("/api/reports", self._valid(), format="json")
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.json()["code"], 40301)

    def test_create_validation_422(self):
        self._auth(self.token)
        cases = [
            (self._valid(title=""), "标题不能为空"),
            (self._valid(conclusion=""), "结论必须为"),
            (self._valid(conclusion="blocker"), "结论必须为"),
            (self._valid(summary=""), "验证内容不能为空"),
        ]
        for payload, expect in cases:
            resp = self.client.post("/api/reports", payload, format="json")
            self.assertEqual(resp.status_code, 422)
            self.assertEqual(resp.json()["code"], 42201)
            self.assertIn(expect, resp.json()["message"])

    def test_version_strategy_must_be_paired(self):
        self._auth(self.token)
        # 只选版本不选策略
        resp = self.client.post("/api/reports", self._valid(strategy_id=None), format="json")
        self.assertEqual(resp.status_code, 422)
        # 只选策略不选版本
        resp = self.client.post("/api/reports", self._valid(version_id=None), format="json")
        self.assertEqual(resp.status_code, 422)
        # 策略不属于所选版本
        pm27b = User.objects.create_user(username="pm27b", password="123456", role="pm")
        v2 = Version.objects.create(name="27B", pm_user=pm27b, status="active")
        b2 = Branch.objects.create(version=v2, name="master")
        s2 = Strategy.objects.create(branch=b2, template=self.tmpl, name="27B-master-晚间",
                                     build_start_time="23:00", push_mode="normal", created_by=self.pm)
        resp = self.client.post("/api/reports", self._valid(strategy_id=s2.id), format="json")
        self.assertEqual(resp.status_code, 422)

    def test_list_and_detail(self):
        self._auth(self.token)
        r1 = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        self.client.post("/api/reports", self._valid(title="第二份", conclusion="risk"), format="json")
        resp = self.client.get("/api/reports")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 2)
        resp = self.client.get(f"/api/reports/{r1['id']}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["title"], "27A 冒烟验证报告")

    def test_list_filters(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        self.client.post("/api/reports", self._valid(title="27B 回归报告", conclusion="fail"), format="json")
        # keyword 命中标题
        resp = self.client.get("/api/reports", {"keyword": "27B"})
        self.assertEqual(len(resp.json()["data"]), 1)
        self.assertEqual(resp.json()["data"][0]["title"], "27B 回归报告")
        # keyword 命中 ID（字符串）
        resp = self.client.get("/api/reports", {"keyword": str(r["id"])})
        self.assertEqual(len(resp.json()["data"]), 1)
        # status / version_id / 未命中
        resp = self.client.get("/api/reports", {"status": "draft"})
        self.assertEqual(len(resp.json()["data"]), 2)
        resp = self.client.get("/api/reports", {"version_id": self.version.id})
        self.assertEqual(len(resp.json()["data"]), 2)
        resp = self.client.get("/api/reports", {"keyword": "不存在的关键词"})
        self.assertEqual(len(resp.json()["data"]), 0)

    def test_update_only_by_author(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        # 非作者 tester2 修改被拒
        self._auth(self._login("tester2"))
        resp = self.client.put(f"/api/reports/{r['id']}", self._valid(title="篡改"), format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], 40301)
        # pm 修改被拒
        self._auth(self._login("pm1"))
        resp = self.client.put(f"/api/reports/{r['id']}", self._valid(title="pm 篡改"), format="json")
        self.assertEqual(resp.status_code, 403)
        # 作者修改成功
        self._auth(self.token)
        resp = self.client.put(f"/api/reports/{r['id']}", self._valid(title="修订后标题", conclusion="risk"), format="json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["title"], "修订后标题")
        self.assertEqual(data["conclusion"], "risk")
        self.assertEqual(data["status"], "draft")

    def test_detail_not_found_404(self):
        self._auth(self.token)
        resp = self.client.get("/api/reports/99999")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["code"], 40401)

    def test_publish_flow(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        resp = self.client.post(
            f"/api/reports/{r['id']}/publish",
            {"screenshot": "data:image/png;base64," + "A" * 100},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["push_status"], "pushed")
        self.assertEqual(data["push_target"], "构建通知群")
        self.assertIn("27A 冒烟验证报告", data["message"])
        self.assertIn("通过", data["message"])
        # 报告状态已更新
        resp = self.client.get(f"/api/reports/{r['id']}")
        rep = resp.json()["data"]
        self.assertEqual(rep["status"], "published")
        self.assertEqual(rep["publish_count"], 1)
        self.assertIsNotNone(rep["published_at"])

    def test_publish_requires_author_and_screenshot(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        # 非作者发布被拒
        self._auth(self._login("builder1"))
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": "x"}, format="json")
        self.assertEqual(resp.status_code, 403)
        # pm 发布被拒
        self._auth(self._login("pm1"))
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": "x"}, format="json")
        self.assertEqual(resp.status_code, 403)
        # 缺少截图
        self._auth(self.token)
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {}, format="json")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], 42201)
        # 截图超 2MB
        huge = "A" * (2 * 1024 * 1024 + 1)
        resp = self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": huge}, format="json")
        self.assertEqual(resp.status_code, 422)

    def test_republish_appends_record(self):
        self._auth(self.token)
        r = self.client.post("/api/reports", self._valid(), format="json").json()["data"]
        img = "data:image/png;base64,AAAA"
        self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": img}, format="json")
        self.client.post(f"/api/reports/{r['id']}/publish", {"screenshot": img}, format="json")
        resp = self.client.get(f"/api/reports/{r['id']}/publishes")
        records = resp.json()["data"]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["publisher_name"], "tester1")
        # 倒序：最新在前
        self.assertGreater(records[0]["id"], records[1]["id"])
        # 报告累计发布 2 次
        self.assertEqual(self.client.get(f"/api/reports/{r['id']}").json()["data"]["publish_count"], 2)

    def test_reports_requires_auth(self):
        resp = self.client.get("/api/reports")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["code"], 40100)
```

- [x] **Step 2: 运行测试确认失败（红）**

```bash
cd backend
python manage.py test build_protection_service.tests.ReportApiTests -v 1
```

Expected: 全部 FAIL（URL `/api/reports` 未注册 → 404，或 ImportError）。**红即正确，此时不要 commit。**

---

### Task 3: 视图与路由实现（转绿）

**Files:**
- Create: `backend/build_protection_service/views/reports.py`
- Modify: `backend/build_protection_service/views/urls.py`

- [x] **Step 1: 创建 `views/reports.py`**

```python
"""验证报告视图：列表/详情/发布暨模拟推送/发布历史。"""
import logging

from django.db.models import Q
from django.utils import timezone

from ..api import err, ok
from ..models import ReportPublishRecord, Strategy, VerificationReport
from . import authed_user, json_resp, parse_body

logger = logging.getLogger("build_protection_service")

WRITE_ROLES = ("builder", "tester")
VALID_CONCLUSIONS = ("pass", "fail", "risk")
MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024  # 2MB
PUSH_TARGET = "构建通知群"


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _report_payload(r):
    """报告序列化（含关联版本/策略名称与作者展示名）。"""
    return {
        "id": r.id,
        "title": r.title,
        "version_id": r.version_id,
        "version_name": r.version.name if r.version else None,
        "strategy_id": r.strategy_id,
        "strategy_name": r.strategy.name if r.strategy else None,
        "conclusion": r.conclusion,
        "environment": r.environment,
        "summary": r.summary,
        "risks": r.risks,
        "remark": r.remark,
        "status": r.status,
        "created_by_id": r.created_by_id,
        "created_by_name": r.created_by.display_name or r.created_by.username,
        "published_at": r.published_at.strftime("%Y-%m-%dT%H:%M:%S") if r.published_at else None,
        "publish_count": r.publish_count,
        "created_at": r.created_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_at": r.updated_at.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _publish_payload(p):
    """发布记录序列化（含截图 base64，供前端历史回显）。"""
    return {
        "id": p.id,
        "publisher_name": p.publisher.display_name or p.publisher.username,
        "push_status": p.push_status,
        "push_target": p.push_target,
        "message": p.message,
        "screenshot": p.screenshot,
        "created_at": p.created_at.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _validate(body):
    """报告字段校验，返回 err 响应或 None。"""
    title = (body.get("title") or "").strip()
    conclusion = body.get("conclusion")
    summary = (body.get("summary") or "").strip()
    if not title:
        return err(42201, "标题不能为空")
    if conclusion not in VALID_CONCLUSIONS:
        return err(42201, "结论必须为 pass/fail/risk")
    if not summary:
        return err(42201, "验证内容不能为空")
    version_id = _to_int(body.get("version_id"))
    strategy_id = _to_int(body.get("strategy_id"))
    if bool(version_id) != bool(strategy_id):
        return err(42201, "版本与策略须同时选择或均不选择")
    if strategy_id:
        try:
            strategy = Strategy.objects.get(pk=strategy_id)
        except Strategy.DoesNotExist:
            return err(42201, "所选策略不存在")
        if strategy.branch.version_id != version_id:
            return err(42201, "策略不属于所选版本")
    return None


def reports_view(request):
    """GET 列表（status/version_id/strategy_id/keyword 过滤）；POST 新建（写角色）。"""
    user, error = authed_user(request)
    if error:
        return error
    if request.method == "GET":
        qs = VerificationReport.objects.select_related("version", "strategy", "created_by")
        status = request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        version_id = request.GET.get("version_id")
        if version_id:
            qs = qs.filter(version_id=_to_int(version_id))
        strategy_id = request.GET.get("strategy_id")
        if strategy_id:
            qs = qs.filter(strategy_id=_to_int(strategy_id))
        keyword = (request.GET.get("keyword") or "").strip()
        if keyword:
            cond = Q(title__icontains=keyword)
            if keyword.isdigit():
                cond |= Q(pk=int(keyword))
            qs = qs.filter(cond)
        qs = qs.order_by("-updated_at")
        return json_resp(ok([_report_payload(r) for r in qs]))

    if request.method == "POST":
        if user.role not in WRITE_ROLES:
            return json_resp(err(40301, "仅测试/构建人员可新建报告"), status=403)
        body = parse_body(request)
        bad = _validate(body)
        if bad:
            return json_resp(bad, status=422)
        report = VerificationReport.objects.create(
            title=(body.get("title") or "").strip(),
            version_id=_to_int(body.get("version_id")),
            strategy_id=_to_int(body.get("strategy_id")),
            conclusion=body.get("conclusion"),
            environment=(body.get("environment") or "").strip(),
            summary=(body.get("summary") or "").strip(),
            risks=(body.get("risks") or "").strip(),
            remark=(body.get("remark") or "").strip(),
            created_by=user,
        )
        return json_resp(ok(_report_payload(report)))
    return json_resp(err(42201, "不支持的请求方法"), status=422)


def report_detail_view(request, rid):
    """GET 详情（全员）；PUT 修改（仅作者且写角色）。"""
    user, error = authed_user(request)
    if error:
        return error
    try:
        report = VerificationReport.objects.select_related("version", "strategy", "created_by").get(pk=rid)
    except VerificationReport.DoesNotExist:
        return json_resp(err(40401, "报告不存在"), status=404)
    if request.method == "GET":
        return json_resp(ok(_report_payload(report)))
    if request.method == "PUT":
        if user.role not in WRITE_ROLES or user.id != report.created_by_id:
            return json_resp(err(40301, "仅报告作者可修改"), status=403)
        body = parse_body(request)
        bad = _validate(body)
        if bad:
            return json_resp(bad, status=422)
        report.title = (body.get("title") or "").strip()
        report.version_id = _to_int(body.get("version_id"))
        report.strategy_id = _to_int(body.get("strategy_id"))
        report.conclusion = body.get("conclusion")
        report.environment = (body.get("environment") or "").strip()
        report.summary = (body.get("summary") or "").strip()
        report.risks = (body.get("risks") or "").strip()
        report.remark = (body.get("remark") or "").strip()
        report.save()
        return json_resp(ok(_report_payload(report)))
    return json_resp(err(42201, "不支持的请求方法"), status=422)


def publish_view(request, rid):
    """POST 发布：校验作者 → 落库发布记录（截图）→ 更新报告状态 → 打印模拟推送日志。"""
    user, error = authed_user(request)
    if error:
        return error
    try:
        report = VerificationReport.objects.select_related("created_by").get(pk=rid)
    except VerificationReport.DoesNotExist:
        return json_resp(err(40401, "报告不存在"), status=404)
    if user.role not in WRITE_ROLES or user.id != report.created_by_id:
        return json_resp(err(40301, "仅报告作者可发布"), status=403)
    if request.method != "POST":
        return json_resp(err(42201, "不支持的请求方法"), status=422)
    body = parse_body(request)
    screenshot = body.get("screenshot") or ""
    if not screenshot:
        return json_resp(err(42201, "缺少页面截图"), status=422)
    if len(screenshot.encode("utf-8")) > MAX_SCREENSHOT_BYTES:
        return json_resp(err(42201, "截图超过 2MB 限制"), status=422)
    conclusion_label = dict(VerificationReport.CONCLUSION_CHOICES).get(report.conclusion, report.conclusion)
    message = f"报告《{report.title}》已发布，结论：{conclusion_label}"
    record = ReportPublishRecord.objects.create(
        report=report, publisher=user, screenshot=screenshot,
        push_status="pushed", push_target=PUSH_TARGET, message=message,
    )
    report.status = "published"
    report.published_at = timezone.now()
    report.publish_count += 1
    report.save()
    # 模拟推送：仅打印日志，不调用任何真实推送服务
    logger.info(
        "[report-push][simulate] target=%s message=%s screenshot_bytes=%d record_id=%d",
        record.push_target, record.message, len(screenshot.encode("utf-8")), record.id,
    )
    return json_resp(ok(_publish_payload(record)))


def publishes_view(request, rid):
    """GET 发布历史（倒序，含截图）。"""
    user, error = authed_user(request)
    if error:
        return error
    try:
        report = VerificationReport.objects.get(pk=rid)
    except VerificationReport.DoesNotExist:
        return json_resp(err(40401, "报告不存在"), status=404)
    records = (
        ReportPublishRecord.objects.filter(report=report)
        .select_related("publisher")
        .order_by("-created_at")
    )
    return json_resp(ok([_publish_payload(p) for p in records]))
```

- [x] **Step 2: 在 `views/urls.py` 注册路由**

先确认文件顶部 import 区包含 `from . import reports`（与 `strategies` 等并列），再在 urlpatterns 末尾追加：

```python
    path("reports", reports.reports_view, name="reports"),
    path("reports/<int:rid>", reports.report_detail_view, name="report_detail"),
    path("reports/<int:rid>/publish", reports.publish_view, name="report_publish"),
    path("reports/<int:rid>/publishes", reports.publishes_view, name="report_publishes"),
```

- [x] **Step 3: 运行测试确认转绿**

```bash
python manage.py test build_protection_service.tests.ReportApiTests -v 1
```

Expected: 全部 PASS（12 个用例）。

- [x] **Step 4: 全量回归**

```bash
python manage.py test build_protection_service -v 1
```

Expected: 全部 PASS。同时检查后端控制台首次发布时出现 `[report-push][simulate]` 日志（仅任务 8 联调时人工可见，测试环境输出可选）。

- [x] **Step 5: Commit**

```bash
git add backend/build_protection_service/views/reports.py backend/build_protection_service/views/urls.py backend/build_protection_service/tests.py
git commit -m "feat: 实现验证报告 API（列表/详情/发布/发布历史）"
```

---

### Task 4: 前端依赖、类型与 API 模块

**Files:**
- Modify: `frontend/package.json`（`pnpm add` 自动追加）
- Modify: `frontend/src/api/types.ts`（末尾追加）
- Create: `frontend/src/api/report.ts`

- [x] **Step 1: 安装 html2canvas**

```bash
cd frontend
pnpm add html2canvas
```

Expected: `package.json` dependencies 出现 `"html2canvas": "^1.4.1"`。html2canvas 自带 TypeScript 类型，无需额外 @types。

- [x] **Step 2: 在 `types.ts` 末尾追加报告类型**

追加到文件末尾（保持现有「按模块分节」注释风格）：

```ts
// ============ 验证报告 ============

/** 验证报告条目 */
export interface ReportItem {
  id: number;
  title: string;
  version_id?: number | null;
  version_name?: string | null;
  strategy_id?: number | null;
  strategy_name?: string | null;
  /** 结论：pass / fail / risk */
  conclusion: string;
  environment: string;
  summary: string;
  risks: string;
  remark: string;
  /** 状态：draft / published */
  status: string;
  created_by_id: number;
  created_by_name: string;
  published_at?: string | null;
  publish_count: number;
  created_at: string;
  updated_at: string;
}

/** 发布暨推送记录（含截图 base64） */
export interface ReportPublishItem {
  id: number;
  publisher_name: string;
  push_status: string;
  push_target: string;
  message: string;
  screenshot: string;
  created_at: string;
}
```

- [x] **Step 3: 创建 `src/api/report.ts`**

```ts
// 验证报告 API 模块
// 契约基准：docs/superpowers/specs/2026-08-15-verification-report-design.md
import http from "@/api/http";
import type { ReportItem, ReportPublishItem } from "@/api/types";

/** 报告表单 */
export interface ReportForm {
  title: string;
  version_id?: number | null;
  strategy_id?: number | null;
  conclusion: string;
  environment?: string;
  summary: string;
  risks?: string;
  remark?: string;
}

/** 报告列表查询 */
export interface ReportQuery {
  status?: string;
  version_id?: number;
  strategy_id?: number;
  keyword?: string;
}

/** 报告列表 */
export function getReports(params?: ReportQuery): Promise<ReportItem[]> {
  return http.get("/reports", { params });
}

/** 报告详情 */
export function getReport(id: number): Promise<ReportItem> {
  return http.get(`/reports/${id}`);
}

/** 新建报告（草稿） */
export function createReport(data: ReportForm): Promise<ReportItem> {
  return http.post("/reports", data);
}

/** 修改报告（仅作者） */
export function updateReport(id: number, data: ReportForm): Promise<ReportItem> {
  return http.put(`/reports/${id}`, data);
}

/** 发布并推送：上传截图，后端落库并打印模拟推送日志 */
export function publishReport(id: number, screenshot: string): Promise<ReportPublishItem> {
  return http.post(`/reports/${id}/publish`, { screenshot });
}

/** 发布历史（倒序，含截图） */
export function getReportPublishes(id: number): Promise<ReportPublishItem[]> {
  return http.get(`/reports/${id}/publishes`);
}
```

- [x] **Step 4: 类型检查**

```bash
pnpm typecheck
```

Expected: 无新增错误（如报既有代码错误可先核对是否为本次改动引入）。

- [x] **Step 5: Commit**

```bash
git add frontend/package.json frontend/src/api/types.ts frontend/src/api/report.ts
git commit -m "feat: 前端新增报告 API 模块与类型定义"
```

---

### Task 5: 前端路由接入

**Files:**
- Modify: `frontend/src/router/asyncRoutes.ts`

- [x] **Step 1: 插入 `/report` 路由模块**

在 `asyncRoutes.ts` 中，紧接 `/strategy` 模块（rank 6，第 148 行 `},` 之后）、`/system` 模块（`{` 之前）插入以下模块：

```ts
  {
    path: "/report",
    name: "Report",
    component: Layout,
    redirect: "/report/index",
    meta: {
      icon: "ep/notebook",
      title: "验证报告",
      rank: 7
    },
    children: [
      {
        path: "/report/index",
        name: "ReportIndex",
        component: () => import("@/views/report/index.vue"),
        meta: {
          title: "验证报告",
          roles: ALL_ROLES
        }
      },
      {
        path: "/report/detail/:id",
        name: "ReportDetail",
        component: () => import("@/views/report/detail.vue"),
        meta: {
          title: "报告详情",
          showLink: false,
          roles: ALL_ROLES
        }
      }
    ]
  },
```

说明：`/report/detail/:id` 为深链接入口（`/#/report/detail/123` 直达指定报告），`showLink: false` 使其不出现在侧边菜单；`:id="new"` 表示新建态。

- [x] **Step 2: 顺延 system/logs 的 rank**

报告占 rank 7 后，原 `system` 模块的 `meta.rank: 7` 改为 `8`、原 `logs` 模块的 `meta.rank: 8` 改为 `9`：

```ts
      icon: "ep/setting",
      title: "系统管理",
      rank: 8
```

```ts
      icon: "ep/document",
      title: "日志中心",
      rank: 9
```

- [x] **Step 3: 类型检查**

```bash
cd frontend
pnpm typecheck
```

Expected: 无新增错误。此时 detail.vue 尚未创建，懒加载路径不校验（vite 仅构建时解析），可先继续 Task 6-7 再统一验证。

- [x] **Step 4: Commit**

```bash
git add frontend/src/router/asyncRoutes.ts
git commit -m "feat: 前端接入验证报告路由（/report 模块，菜单 rank 7）"
```

---

### Task 6: 报告列表页

**Files:**
- Create: `frontend/src/views/report/index.vue`

- [x] **Step 1: 创建列表页脚本与模板**

整体风格沿用 `strategy/index.vue` / `plan/index.vue` 的白底圆角 `.filter-bar` / `.section` 范式：

```vue
<script setup lang="ts">
// 验证报告列表页：筛选 / 表格 / 复制链接 / 新建
// 权限：tester/builder 可新建，编辑仅作者，其余角色只读（设计文档 4.2）
import { ref, reactive, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { getReports, type ReportQuery } from "@/api/report";
import { getStrategies } from "@/api/strategy";
import type { ReportItem, StrategyItem } from "@/api/types";
import { getCurrentUser, formatTime } from "@/utils/business";

defineOptions({ name: "ReportIndex" });

const router = useRouter();
const currentUser = getCurrentUser();

// ---- 权限 ----
const canWrite = computed(
  () => currentUser?.role === "tester" || currentUser?.role === "builder"
);
function canEdit(row: ReportItem) {
  return canWrite.value && currentUser?.id === row.created_by_id;
}

// ---- 筛选 ----
const loading = ref(false);
const list = ref<ReportItem[]>([]);
const filter = reactive<ReportQuery>({
  keyword: "",
  status: undefined,
  version_id: undefined,
  strategy_id: undefined
});

// 版本/策略级联选项：从全量策略推导（策略自带版本归属）
const allStrategies = ref<StrategyItem[]>([]);
const versionOptions = computed(() => {
  const map = new Map<number, string>();
  allStrategies.value.forEach(s => {
    if (s.version_id != null && !map.has(s.version_id)) {
      map.set(s.version_id, s.version_name);
    }
  });
  return Array.from(map, ([id, name]) => ({ id, name }));
});
const strategyOptions = computed(() =>
  allStrategies.value.filter(s => s.version_id === filter.version_id)
);

function onVersionChange() {
  filter.strategy_id = undefined;
  load();
}

async function load() {
  loading.value = true;
  try {
    list.value = await getReports({ ...filter });
  } finally {
    loading.value = false;
  }
}

// ---- 徽章映射 ----
const conclusionMap: Record<string, { text: string; type: "success" | "danger" | "warning" | "info" }> = {
  pass: { text: "通过", type: "success" },
  fail: { text: "不通过", type: "danger" },
  risk: { text: "有风险", type: "warning" }
};
const statusMap: Record<string, { text: string; type: "info" | "success" }> = {
  draft: { text: "草稿", type: "info" },
  published: { text: "已发布", type: "success" }
};
function conclusionTag(c: string) {
  return conclusionMap[c] || { text: c, type: "info" as const };
}
function statusTag(s: string) {
  return statusMap[s] || { text: s, type: "info" as const };
}

// ---- 操作 ----
// 深链接：hash 路由下浏览器地址即 {origin}/#/report/detail/{id}
const reportLink = (id: number) => `${window.location.origin}/#/report/detail/${id}`;

async function copyLink(row: ReportItem) {
  const url = reportLink(row.id);
  try {
    await navigator.clipboard.writeText(url);
  } catch {
    // 降级：非 HTTPS 或浏览器限制时用临时 textarea 复制
    const ta = document.createElement("textarea");
    ta.value = url;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  ElMessage.success("链接已复制，可直接粘贴分享");
}

function goDetail(row: ReportItem) {
  router.push(`/report/detail/${row.id}`);
}
function goEdit(row: ReportItem) {
  router.push({ path: `/report/detail/${row.id}`, query: { edit: "1" } });
}
function goCreate() {
  router.push("/report/detail/new");
}

onMounted(async () => {
  load();
  try {
    allStrategies.value = await getStrategies();
  } catch {
    allStrategies.value = [];
  }
});
</script>

<template>
  <div class="report-page">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-left">
        <el-select
          v-model="filter.status"
          placeholder="全部状态"
          clearable
          style="width: 130px"
          @change="load"
        >
          <el-option label="草稿" value="draft" />
          <el-option label="已发布" value="published" />
        </el-select>
        <el-select
          v-model="filter.version_id"
          placeholder="全部版本"
          clearable
          style="width: 150px"
          @change="onVersionChange"
        >
          <el-option v-for="v in versionOptions" :key="v.id" :label="v.name" :value="v.id" />
        </el-select>
        <el-select
          v-model="filter.strategy_id"
          placeholder="全部策略"
          clearable
          :disabled="!filter.version_id"
          style="width: 190px"
          @change="load"
        >
          <el-option v-for="s in strategyOptions" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <el-input
          v-model="filter.keyword"
          placeholder="标题 / ID 搜索"
          clearable
          style="width: 180px"
          @keyup.enter="load"
        />
        <el-button type="primary" :loading="loading" @click="load">查询</el-button>
      </div>
      <el-button v-if="canWrite" type="primary" @click="goCreate">新建报告</el-button>
    </div>

    <!-- 报告表格 -->
    <div class="section">
      <el-table :data="list" v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="标题" min-width="220">
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="goDetail(row as ReportItem)">
              {{ row.title }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column label="关联策略" min-width="200">
          <template #default="{ row }">
            <template v-if="row.version_name && row.strategy_name">
              {{ row.version_name }} / {{ row.strategy_name }}
            </template>
            <span v-else class="no-link">-</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="90">
          <template #default="{ row }">
            <el-tag :type="conclusionTag(row.conclusion).type" size="small">
              {{ conclusionTag(row.conclusion).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status).type" size="small">
              {{ statusTag(row.status).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by_name" label="作者" width="110" />
        <el-table-column label="更新时间" width="140">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="goDetail(row as ReportItem)">
              查看
            </el-button>
            <el-button type="primary" link size="small" @click="copyLink(row as ReportItem)">
              复制链接
            </el-button>
            <el-button
              v-if="canEdit(row as ReportItem)"
              type="primary"
              link
              size="small"
              @click="goEdit(row as ReportItem)"
            >
              编辑
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && list.length === 0" description="暂无报告" />
    </div>
  </div>
</template>

<style scoped>
.report-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 16px;
}
.filter-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.section {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}
.no-link {
  color: #c0c4cc;
}
</style>
```

- [x] **Step 2: 类型检查与冒烟**

```bash
cd frontend
pnpm typecheck
pnpm dev
```

Expected: typecheck 无新增错误、dev 正常启动。侧边菜单出现「验证报告」（位于策略配置与系统管理之间）。此时 detail.vue 尚不存在，点击任意行会因路由组件缺失报错 —— 属预期，Task 7 补齐。

- [x] **Step 3: Commit**

```bash
git add frontend/src/views/report/index.vue
git commit -m "feat: 新增验证报告列表页（筛选/复制链接/新建入口）"
```

---

### Task 7: 报告详情/编辑页（截图发布 + 发布历史）

**Files:**
- Create: `frontend/src/views/report/detail.vue`

- [x] **Step 1: 创建详情页（脚本 + 模板）**

将下面的 `<script>` 与 `<template>` 两段依次写入 `frontend/src/views/report/detail.vue`（`<style>` 在 Step 2 追加）。关键机制：

- `routeId`/`isNew` 用 `computed` 随 `route.params.id` 变化 —— 新建保存后 `router.replace` 到真实 id，页面自动从「新建态」切换为「已存在」模式（同一组件实例不重挂载）；
- `cardData` 为统一卡片数据源：编辑态实时用 form 覆盖（所见即所截），保证截图目标恒存在；
- 发布流程：`saveDraft()`（新建走 create → replace）→ `nextTick` + 100ms 等待渲染 → `html2canvas(el, {scale:2, backgroundColor:"#ffffff", useCORS:true})` → base64 前端按 0.75 系数估算字节数校验 2MB → `publishReport(id, screenshot)` → 刷新报告与发布历史；
- 40401（报告不存在）→ `router.replace("/report/index")`。

```vue
<script setup lang="ts">
// 验证报告详情/编辑页：只读展示 / 编辑表单 / 截图发布 / 发布历史
// 权限：tester/builder 且作者可编辑发布；新建态天然为编辑态
import { ref, reactive, computed, onMounted, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import html2canvas from "html2canvas";
import {
  getReport,
  createReport,
  updateReport,
  publishReport,
  getReportPublishes,
  type ReportForm
} from "@/api/report";
import { getStrategies } from "@/api/strategy";
import type { ReportItem, ReportPublishItem, StrategyItem } from "@/api/types";
import { getCurrentUser, formatTime } from "@/utils/business";

defineOptions({ name: "ReportDetail" });

const route = useRoute();
const router = useRouter();
const currentUser = getCurrentUser();

const MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024; // 2MB，与后端校验一致

// ---- 路由态 ----
const routeId = computed(() => String(route.params.id ?? ""));
const isNew = computed(() => routeId.value === "new");

// ---- 权限 ----
const canWrite = computed(
  () => currentUser?.role === "tester" || currentUser?.role === "builder"
);
function canEdit(row: ReportItem) {
  return canWrite.value && currentUser?.id === row.created_by_id;
}
const canEditCurrent = computed(() => (report.value ? canEdit(report.value) : false));

// ---- 数据 ----
const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const report = ref<ReportItem | null>(null);
const publishes = ref<ReportPublishItem[]>([]);
const activePublish = ref<number>(0);
const cardWrapRef = ref<HTMLElement | null>(null);
const editing = ref(isNew.value); // 新建态初始为编辑态；详情默认只读

// ---- 版本/策略选项（从全量策略推导，与列表页一致）----
const allStrategies = ref<StrategyItem[]>([]);
const versionOptions = computed(() => {
  const map = new Map<number, string>();
  allStrategies.value.forEach(s => {
    if (s.version_id != null && !map.has(s.version_id)) {
      map.set(s.version_id, s.version_name);
    }
  });
  return Array.from(map, ([id, name]) => ({ id, name }));
});
const strategyOptions = computed(() =>
  allStrategies.value.filter(s => s.version_id === form.version_id)
);
function versionNameOf(id?: number | null) {
  return allStrategies.value.find(s => s.version_id === id)?.version_name || null;
}
function strategyNameOf(id?: number | null) {
  return allStrategies.value.find(s => s.id === id)?.name || null;
}
function onVersionChange() {
  form.strategy_id = null;
}

// ---- 表单 ----
const form = reactive<ReportForm>({
  title: "",
  version_id: null,
  strategy_id: null,
  conclusion: "pass",
  environment: "",
  summary: "",
  risks: "",
  remark: ""
});

function fillForm(r: ReportItem) {
  form.title = r.title;
  form.version_id = r.version_id ?? null;
  form.strategy_id = r.strategy_id ?? null;
  form.conclusion = r.conclusion;
  form.environment = r.environment;
  form.summary = r.summary;
  form.risks = r.risks;
  form.remark = r.remark;
}

function startEdit() {
  if (report.value) {
    fillForm(report.value);
    editing.value = true;
  }
}
function cancelEdit() {
  if (report.value) fillForm(report.value);
  editing.value = false;
}

// ---- 卡片数据源（编辑态实时预览，保证截图目标恒存在）----
const cardData = computed(() => {
  const base = report.value;
  if (editing.value || isNew.value) {
    return {
      title: form.title.trim() || "（未填写标题）",
      version_name: versionNameOf(form.version_id),
      strategy_name: strategyNameOf(form.strategy_id),
      conclusion: form.conclusion,
      status: base?.status || "draft",
      environment: form.environment,
      summary: form.summary,
      risks: form.risks,
      remark: form.remark,
      created_by_name:
        base?.created_by_name ||
        currentUser?.display_name ||
        currentUser?.username ||
        "",
      updated_at: base?.updated_at || null
    };
  }
  return {
    title: base?.title || "",
    version_name: base?.version_name || null,
    strategy_name: base?.strategy_name || null,
    conclusion: base?.conclusion || "",
    status: base?.status || "",
    environment: base?.environment || "",
    summary: base?.summary || "",
    risks: base?.risks || "",
    remark: base?.remark || "",
    created_by_name: base?.created_by_name || "",
    updated_at: base?.updated_at || null
  };
});

// ---- 徽章映射（与列表页一致）----
const conclusionMap: Record<string, { text: string; type: "success" | "danger" | "warning" | "info" }> = {
  pass: { text: "通过", type: "success" },
  fail: { text: "不通过", type: "danger" },
  risk: { text: "有风险", type: "warning" }
};
const statusMap: Record<string, { text: string; type: "info" | "success" }> = {
  draft: { text: "草稿", type: "info" },
  published: { text: "已发布", type: "success" }
};
function conclusionTag(c: string) {
  return conclusionMap[c] || { text: c, type: "info" as const };
}
function statusTag(s: string) {
  return statusMap[s] || { text: s, type: "info" as const };
}

// ---- 校验 ----
function validateForm(): boolean {
  if (!form.title.trim()) {
    ElMessage.warning("请填写报告标题");
    return false;
  }
  if (!form.conclusion) {
    ElMessage.warning("请选择验证结论");
    return false;
  }
  if (!form.summary.trim()) {
    ElMessage.warning("请填写验证内容");
    return false;
  }
  if (!!form.version_id !== !!form.strategy_id) {
    ElMessage.warning("版本与策略须同时选择或均不选择");
    return false;
  }
  return true;
}

function toPayload(): ReportForm {
  return {
    title: form.title.trim(),
    version_id: form.version_id || null,
    strategy_id: form.strategy_id || null,
    conclusion: form.conclusion,
    environment: form.environment.trim(),
    summary: form.summary.trim(),
    risks: form.risks.trim(),
    remark: form.remark.trim()
  };
}

// ---- 加载 ----
async function loadReport() {
  if (isNew.value) return;
  loading.value = true;
  try {
    const data = await getReport(Number(routeId.value));
    report.value = data;
    fillForm(data);
    // 深链接带 ?edit=1 且为作者时直达编辑态
    if (route.query.edit === "1" && canEdit(data)) {
      editing.value = true;
    }
  } catch (e: any) {
    const code = e?.response?.data?.code ?? e?.code;
    if (code === 40401) {
      ElMessage.error("报告不存在或已删除");
      router.replace("/report/index");
    }
  } finally {
    loading.value = false;
  }
}

async function loadPublishes() {
  if (isNew.value) {
    publishes.value = [];
    return;
  }
  if (!report.value) return;
  publishes.value = await getReportPublishes(report.value.id);
  if (publishes.value.length && !activePublish.value) {
    activePublish.value = publishes.value[0].id; // 默认展开最新一条
  }
}

// ---- 保存 ----
async function saveDraft(): Promise<ReportItem | null> {
  if (!validateForm()) return null;
  saving.value = true;
  try {
    if (isNew.value) {
      const saved = await createReport(toPayload());
      report.value = saved;
      await router.replace(`/report/detail/${saved.id}`);
      editing.value = true; // 保存后仍留在编辑态，便于继续完善后再发布
      ElMessage.success("报告已创建，可继续编辑或直接发布");
      await loadPublishes();
      return saved;
    }
    if (!report.value) return null;
    const saved = await updateReport(report.value.id, toPayload());
    report.value = saved;
    ElMessage.success("报告已保存");
    return saved;
  } finally {
    saving.value = false;
  }
}

// ---- 截图与发布 ----
async function captureCard(): Promise<string> {
  const el = cardWrapRef.value;
  if (!el) throw new Error("截图区域不存在");
  const canvas = await html2canvas(el, {
    scale: 2,
    backgroundColor: "#ffffff",
    useCORS: true,
    logging: false
  });
  return canvas.toDataURL("image/png");
}

/** base64 字节数估算（dataURL 主体 4 字符 ≈ 3 字节） */
function base64Bytes(dataUrl: string): number {
  const body = dataUrl.split(",")[1] || "";
  return Math.floor(body.length * 0.75);
}

async function onPublish() {
  if (!validateForm()) return;
  try {
    await ElMessageBox.confirm(
      "发布后将模拟推送至「构建通知群」，并记录当前报告页面截图。确认发布？",
      "发布报告",
      { type: "warning", confirmButtonText: "确认发布", cancelButtonText: "取消" }
    );
  } catch {
    return; // 用户取消
  }
  publishing.value = true;
  try {
    const saved = await saveDraft();
    if (!saved) return;
    // 等路由替换与卡片重渲染完成再截图
    await nextTick();
    await new Promise(resolve => setTimeout(resolve, 100));
    const screenshot = await captureCard();
    if (base64Bytes(screenshot) > MAX_SCREENSHOT_BYTES) {
      ElMessage.error("截图超过 2MB，请精简报告内容后重试");
      return;
    }
    await publishReport(saved.id, screenshot);
    ElMessage.success("发布成功，已模拟推送至构建通知群");
    await loadReport();
    await loadPublishes();
    if (isNew.value) editing.value = false; // 新建发布完成后转为只读展示
  } catch {
    // http.ts 已统一按错误码提示
  } finally {
    publishing.value = false;
  }
}

// ---- 复制链接 ----
const reportLink = computed(() =>
  `${window.location.origin}/#/report/detail/${routeId.value}`
);
async function copyLink() {
  try {
    await navigator.clipboard.writeText(reportLink.value);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = reportLink.value;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  ElMessage.success("链接已复制");
}

onMounted(async () => {
  await loadReport();
  await loadPublishes();
  try {
    allStrategies.value = await getStrategies();
  } catch {
    allStrategies.value = [];
  }
});
</script>

<template>
  <div class="report-detail" v-loading="loading">
    <!-- 顶部操作栏（非新建） -->
    <div v-if="!isNew && report" class="op-bar">
      <div class="op-left">
        <span class="op-title">报告 #{{ report.id }}</span>
      </div>
      <div class="op-right">
        <el-button @click="copyLink">复制链接</el-button>
        <el-button v-if="canEditCurrent && !editing" type="primary" @click="startEdit">编辑</el-button>
        <el-button v-if="canEditCurrent" type="success" :loading="publishing" @click="onPublish">发布</el-button>
      </div>
    </div>

    <!-- 报告卡片（恒存在，截图目标） -->
    <div
      v-if="report || editing"
      ref="cardWrapRef"
      class="section report-card-wrap"
    >
      <div class="report-card">
        <div class="card-head">
          <span class="card-title">{{ cardData.title }}</span>
          <span class="card-tags">
            <el-tag :type="conclusionTag(cardData.conclusion).type" size="small">
              {{ conclusionTag(cardData.conclusion).text }}
            </el-tag>
            <el-tag
              v-if="cardData.status"
              :type="statusTag(cardData.status).type"
              size="small"
            >
              {{ statusTag(cardData.status).text }}
            </el-tag>
          </span>
        </div>
        <div class="card-meta">
          <template v-if="cardData.version_name && cardData.strategy_name">
            关联策略：{{ cardData.version_name }} / {{ cardData.strategy_name }}
          </template>
          <span v-else>未关联策略</span>
        </div>
        <div class="card-body">
          <div v-if="cardData.environment" class="card-section">
            <span class="sec-label">验证环境</span>
            <span class="sec-text">{{ cardData.environment }}</span>
          </div>
          <div class="card-section">
            <span class="sec-label">验证内容</span>
            <p class="sec-text">{{ cardData.summary }}</p>
          </div>
          <div v-if="cardData.risks" class="card-section">
            <span class="sec-label">问题与风险</span>
            <p class="sec-text">{{ cardData.risks }}</p>
          </div>
          <div v-if="cardData.remark" class="card-section">
            <span class="sec-label">备注</span>
            <p class="sec-text">{{ cardData.remark }}</p>
          </div>
        </div>
        <div class="card-foot">
          <span>作者：{{ cardData.created_by_name }}</span>
          <span v-if="cardData.updated_at">
            更新于 {{ formatTime(cardData.updated_at, "YYYY-MM-DD HH:mm") }}
          </span>
        </div>
      </div>
    </div>

    <!-- 新建 / 编辑表单 -->
    <div v-if="editing" class="section">
      <div class="section-title">{{ isNew ? "新建验证报告" : "编辑报告内容" }}</div>
      <el-form :model="form" label-width="100px" class="report-form">
        <el-form-item label="报告标题" required>
          <el-input v-model="form.title" placeholder="例：27A 冒烟验证报告" style="width: 420px" />
        </el-form-item>
        <el-form-item label="关联版本">
          <el-select
            v-model="form.version_id"
            placeholder="可选"
            clearable
            style="width: 200px"
            @change="onVersionChange"
          >
            <el-option v-for="v in versionOptions" :key="v.id" :label="v.name" :value="v.id" />
          </el-select>
          <span class="form-tip">版本与策略须同时选择或均不选择</span>
        </el-form-item>
        <el-form-item label="关联策略">
          <el-select
            v-model="form.strategy_id"
            placeholder="可选"
            clearable
            :disabled="!form.version_id"
            style="width: 280px"
          >
            <el-option v-for="s in strategyOptions" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="验证结论" required>
          <el-radio-group v-model="form.conclusion">
            <el-radio value="pass">通过</el-radio>
            <el-radio value="fail">不通过</el-radio>
            <el-radio value="risk">有风险</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="验证环境">
          <el-input
            v-model="form.environment"
            placeholder="例：测试环境 / 生产预发"
            style="width: 420px"
          />
        </el-form-item>
        <el-form-item label="验证内容" required>
          <el-input
            v-model="form.summary"
            type="textarea"
            :rows="4"
            placeholder="填写验证内容，将展示在报告卡片中"
            style="width: 560px"
          />
        </el-form-item>
        <el-form-item label="问题与风险">
          <el-input v-model="form.risks" type="textarea" :rows="3" placeholder="可选" style="width: 560px" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="可选" style="width: 560px" />
        </el-form-item>
      </el-form>
      <div class="form-actions">
        <el-button type="primary" :loading="saving" @click="saveDraft">保存草稿</el-button>
        <el-button type="success" :loading="publishing" @click="onPublish">保存并发布</el-button>
        <el-button v-if="!isNew" @click="cancelEdit">取消</el-button>
      </div>
    </div>

    <!-- 发布历史（非新建） -->
    <div v-if="!isNew" class="section">
      <div class="section-title">发布历史（{{ publishes.length }}）</div>
      <el-empty
        v-if="publishes.length === 0"
        description="暂无发布记录"
        :image-size="60"
      />
      <el-collapse v-else v-model="activePublish" accordion class="pub-collapse">
        <el-collapse-item v-for="p in publishes" :key="p.id" :name="p.id">
          <template #title>
            <span>{{ formatTime(p.created_at, "YYYY-MM-DD HH:mm") }} · {{ p.publisher_name }}</span>
            <el-tag
              size="small"
              :type="p.push_status === 'pushed' ? 'success' : 'info'"
              style="margin-left: 8px"
            >
              {{ p.push_status === "pushed" ? "已推送" : p.push_status }}
            </el-tag>
          </template>
          <div class="pub-item">
            <el-image
              :src="p.screenshot"
              :preview-src-list="[p.screenshot]"
              fit="contain"
              class="pub-img"
              preview-teleported
            />
            <p class="pub-message">{{ p.message }}</p>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>
```

- [x] **Step 2: 追加样式**

将下面的 `<style scoped>` 整体追加到 `frontend/src/views/report/detail.vue` 末尾（`</template>` 之后）：

```vue
<style scoped>
.report-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.op-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 16px;
}
.op-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
.op-right {
  display: flex;
  gap: 8px;
}
.section {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}
.section-title {
  color: #303133;
  font-weight: 600;
  margin-bottom: 12px;
}
.form-tip {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}
.form-actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}
/* 报告卡片：截图区域 */
.report-card-wrap {
  padding: 0;
  overflow: hidden;
}
.report-card {
  background: #fff;
  padding: 20px 24px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #f0f2f5;
  padding-bottom: 12px;
}
.card-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.card-tags {
  display: inline-flex;
  gap: 6px;
  flex-shrink: 0;
}
.card-meta {
  color: #909399;
  font-size: 13px;
  padding: 10px 0;
  border-bottom: 1px dashed #f0f2f5;
}
.card-body {
  padding: 12px 0;
}
.card-section {
  margin-bottom: 10px;
  font-size: 14px;
  line-height: 1.7;
  color: #303133;
}
.sec-label {
  display: inline-block;
  color: #909399;
  font-size: 13px;
  margin-right: 10px;
}
.sec-text {
  white-space: pre-wrap;
  margin: 0;
}
.card-foot {
  display: flex;
  justify-content: space-between;
  color: #c0c4cc;
  font-size: 12px;
  border-top: 1px solid #f0f2f5;
  padding-top: 10px;
}
.pub-collapse {
  border-top: none;
}
.pub-item {
  padding: 4px 8px;
}
.pub-img {
  display: block;
  max-width: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  margin-bottom: 8px;
}
.pub-message {
  color: #606266;
  font-size: 13px;
}
</style>
```

- [x] **Step 3: 类型检查与浏览器验证**

```bash
cd frontend
pnpm typecheck
```

Expected: 无新增错误。随后启动 `pnpm dev` 在浏览器中验证（可结合 chrome-devtools）：

1. 列表页 → 报告标题 el-link 点击 → 进入详情页（只读展示报告卡片、关联版本/策略名称正确显示）；
2. 新建报告（`/report/detail/new`）→ 填写标题/结论/内容 → 保存草稿 → 地址栏自动切换为 `/report/detail/{id}`，出现发布历史区与操作栏；
3. 编辑 → 修改验证内容 → 卡片实时更新 → 「保存并发布」→ 弹窗确认 → 收到「已模拟推送至构建通知群」提示；
4. 发布历史区出现最新记录，展开可见截图（el-image 预览放大）与推送摘要；
5. 再次编辑重发 → 发布历史出现两条记录（倒序）；
6. 顶部「复制链接」→ 新标签页打开 `{origin}/#/report/detail/{id}` → 直达报告详情；
7. 非作者/无权限角色访问（如 pm）→ 无「编辑」「发布」按钮，仅只读；
8. 快速访问不存在的 id → 自动跳回列表页。

- [x] **Step 4: Commit**

```bash
git add frontend/src/views/report/detail.vue
git commit -m "feat: 新增验证报告详情页（截图发布/发布历史/深链接直达）"
```

---

### Task 8: 端到端联调验证

**目的：** 前后端串起来走完整业务流程，确认截图上传、模拟推送日志、深链接、权限控制全部符合 spec。

- [x] **Step 1: 后端启动（后台运行）**

```bash
cd backend
.\.venv\Scripts\python.exe manage.py runserver 8000
```

Expected: 后端监听 8000，无迁移告警。

- [x] **Step 2: 前端启动（后台运行）**

```bash
cd frontend
pnpm dev
```

Expected: 前端运行于 8848 端口。

- [x] **Step 3: 浏览器全流程验证（chrome-devtools）**

用 `tester / 123456` 登录后逐项确认：

1. 侧边菜单顺序：… → 策略配置 → **验证报告** → 系统管理 → …（验证报告插在 6 与 8 之间，rank 7）；
2. 列表页默认展示全部报告；筛选（状态/版本/策略/关键字）可用；
3. 新建报告：关联版本选 `27A`、策略选 `27A-master`，保存草稿成功，地址栏自动切到 `/report/detail/{id}`；
4. 保存并发布：确认弹窗 → 截图上传 → 成功提示「已模拟推送至构建通知群」；
5. 后端控制台出现 `[report-push][simulate] target=构建通知群 message=… screenshot_bytes=… record_id=…` 日志（仅打印，不发真实推送）；
6. 发布历史区：最新记录默认展开，截图回显、可放大预览，推送状态「已推送」；
7. 再次编辑（标题加后缀）重发 → 发布历史两条记录倒序；
8. 复制链接 → 新标签页直达报告详情；
9. 用 `pm` 登录：无「新建报告」「编辑」「发布」按钮（只读）；
10. 用 `builder` 登录：不能编辑 tester 创建的报告（无编辑按钮）。

- [x] **Step 4: 全量回归**

```bash
cd backend
python manage.py test build_protection_service -v 1
```

Expected: 全部 PASS（含既有模块与 ReportApiTests）。

```bash
cd frontend
pnpm typecheck
```

Expected: 无错误。

- [x] **Step 5: 收尾提交（仅当存在未提交改动时）**

```bash
git status
```

如有残留未提交文件：

```bash
git add -A
git commit -m "chore: 验证报告功能联调验证通过"
```

---

**恭喜：至此验证报告功能全部落地。** 交付物回顾：后端模型/API（Task 1-3）、前端 API 层（Task 4）、路由（Task 5）、列表页（Task 6）、详情页（Task 7）、端到端联调（Task 8）。