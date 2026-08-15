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