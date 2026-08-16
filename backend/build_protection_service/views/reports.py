"""验证报告视图集：列表/详情/新建/修改 + 发布/修改记录（DRF ViewSet，废弃功能已移除）。"""
import logging
from typing import Dict, Optional

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from ..api import err, ok
from ..filters.report import ReportFilter
from ..models import VerificationReport
from ..serializers.report import ReportRevisionLogSerializer, ReportSerializer
from ..services.report_service import ReportConclusionLockedError, ReportService
from . import authed_user, json_resp

logger = logging.getLogger("build_protection_service")

WRITE_ROLES = ("builder", "tester")
MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024  # 2MB
PUSH_TARGET = "构建通知群"


class ReportViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """验证报告视图集：报告独立单表 + 修改记录留痕，统一 401/403/404/422 错误码。"""

    queryset = VerificationReport.objects.all()
    serializer_class = ReportSerializer
    # 认证由 authed_user 手动校验，DRF 全局 IsAuthenticated 只做放行，
    # 否则未认证请求会被 DRF 拦截返回无 code 的 401，破坏统一响应契约。
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ReportFilter
    http_method_names = ["get", "post", "put", "head", "options"]

    @staticmethod
    def _report(pk: int) -> Optional[VerificationReport]:
        """按主键取报告，不存在返回 None。"""
        try:
            return VerificationReport.objects.get(pk=pk)
        except VerificationReport.DoesNotExist:
            return None

    @staticmethod
    def _first_error(errors: Dict) -> str:
        """取 serializer 错误中的第一条消息用于统一错误提示。"""
        for value in errors.values():
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str) and value:
                return value
        return "参数校验失败"

    def list(self, request, *args, **kwargs):
        """报告列表：status / version_name / strategy_name / keyword 过滤，统一响应封装。"""
        _, error = authed_user(request)
        if error:
            return error
        qs = self.filter_queryset(self.get_queryset())
        return json_resp(ok(ReportSerializer(qs, many=True).data))

    def retrieve(self, request, *args, **kwargs):
        """报告详情。"""
        _, error = authed_user(request)
        if error:
            return error
        report = self._report(kwargs.get("pk"))
        if report is None:
            return json_resp(err(40401, "报告不存在"), status=404)
        return json_resp(ok(ReportSerializer(report).data))

    def create(self, request, *args, **kwargs):
        """新建草稿报告（写角色），写入创建留痕。"""
        user, error = authed_user(request)
        if error:
            return error
        if user.role not in WRITE_ROLES:
            return json_resp(err(40301, "仅测试/构建人员可新建报告"), status=403)
        serializer = ReportSerializer(data=request.data)
        if not serializer.is_valid():
            return json_resp(err(42201, self._first_error(serializer.errors)), status=422)
        report = ReportService.create(user.username, serializer.validated_data)
        return json_resp(ok(ReportSerializer(report).data))

    def update(self, request, *args, **kwargs):
        """修改报告（仅作者且写角色）：发布后可改但结论锁定，字段级 diff 留痕。"""
        user, error = authed_user(request)
        if error:
            return error
        report = self._report(kwargs.get("pk"))
        if report is None:
            return json_resp(err(40401, "报告不存在"), status=404)
        if user.role not in WRITE_ROLES or report.created_by_username != user.username:
            return json_resp(err(40301, "仅报告作者可修改"), status=403)
        serializer = ReportSerializer(report, data=request.data)
        if not serializer.is_valid():
            return json_resp(err(42201, self._first_error(serializer.errors)), status=422)
        try:
            report = ReportService.update(user.username, report, serializer.validated_data)
        except ReportConclusionLockedError as exc:
            return json_resp(err(42201, str(exc)), status=422)
        return json_resp(ok(ReportSerializer(report).data))

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """发布报告：校验截图，重复发布标记为更新发布，刷新发布时间与发布次数。"""
        user, error = authed_user(request)
        if error:
            return error
        report = self._report(pk)
        if report is None:
            return json_resp(err(40401, "报告不存在"), status=404)
        if user.role not in WRITE_ROLES or report.created_by_username != user.username:
            return json_resp(err(40301, "仅报告作者可发布"), status=403)
        screenshot = (request.data or {}).get("screenshot") or ""
        if not screenshot:
            return json_resp(err(42201, "缺少页面截图"), status=422)
        if len(screenshot.encode("utf-8")) > MAX_SCREENSHOT_BYTES:
            return json_resp(err(42201, "截图超过 2MB 限制"), status=422)
        update_mark = "（更新发布）" if report.publish_count > 0 else ""
        conclusion_label = dict(VerificationReport.CONCLUSION_CHOICES).get(
            report.conclusion, report.conclusion
        )
        message = f"报告《{report.title}》已发布{update_mark}，结论：{conclusion_label}"
        report = ReportService.publish(user.username, report)
        # 模拟推送：仅打印日志，不调用任何真实推送服务；截图随日志校验字节数，不落库
        logger.info(
            "[report-push][simulate] target=%s message=%s screenshot_bytes=%d",
            PUSH_TARGET, message, len(screenshot.encode("utf-8")),
        )
        return json_resp(ok(ReportSerializer(report).data))

    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        """报告修改记录：按时间倒序（由近及远）返回创建/修改/发布全部留痕。"""
        _, error = authed_user(request)
        if error:
            return error
        report = self._report(pk)
        if report is None:
            return json_resp(err(40401, "报告不存在"), status=404)
        logs = ReportService.revisions(report.id)
        return json_resp(ok(ReportRevisionLogSerializer(logs, many=True).data))