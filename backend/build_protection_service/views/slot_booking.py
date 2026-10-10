"""时段抢占视图：模板/日历/抢占/释放（DRF ViewSet + 函数视图）。

认证与错误码约定同 reports 模块：ViewSet 置 AllowAny，authed_user 手动校验；
统一响应 {code, message, data}；重名/删除拦截用 40902，抢占冲突新增 40904。
"""
import logging

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from ..api import err, ok
from ..errors import CODE_STATUS
from ..models import SlotBooking, SlotTemplate
from ..serializers.slot_booking import (
    ReleaseBookingSerializer,
    SlotBookingCreateSerializer,
    SlotTemplateSerializer,
)
from ..services.slot_booking import (
    build_slot_calendar,
    create_booking,
    detect_template_overlap,
    release_booking,
    serialize_booking_row,
    serialize_template,
)
from . import authed_user, fail_resp, first_error, json_resp, require_admin

logger = logging.getLogger("build_protection_service")


def _err_resp(error: dict):
    """服务层错误 dict（{code, message}）→ 统一响应（HTTP 状态由公共映射决定）。"""
    return json_resp(err(error["code"], error["message"]),
                     status=CODE_STATUS.get(error["code"], 400))


def _require_admin(user):
    return require_admin(user, message="无权限执行该操作")


def _paginate(qs, request, serializer) -> dict:
    """简单页码分页：page 从 1 起，page_size 默认 20 最大 100。"""
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(100, max(1, int(request.query_params.get("page_size", 20))))
    except (TypeError, ValueError):
        page_size = 20
    total = qs.count()
    rows = qs[(page - 1) * page_size: page * page_size]
    return {"items": [serializer(r) for r in rows], "total": total, "page": page, "page_size": page_size}


class SlotTemplateViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """时段模板：列表（全员，含停用供配置页）/ 新建 / 修改 / 删除（admin）。"""

    queryset = SlotTemplate.objects.all()
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "put", "delete", "head", "options"]

    def list(self, request, *args, **kwargs):
        _, resp = authed_user(request)
        if resp:
            return resp
        qs = self.get_queryset().order_by("sort_order", "id")
        return json_resp(ok([serialize_template(t) for t in qs]))

    def create(self, request, *args, **kwargs):
        user, resp = authed_user(request)
        if resp:
            return resp
        perr = _require_admin(user)
        if perr:
            return perr
        serializer = SlotTemplateSerializer(data=request.data or {})
        if not serializer.is_valid():
            return fail_resp(42201, first_error(serializer.errors))
        template = serializer.save()
        logger.info("[slot-booking] template create id=%s name=%s actor=%s",
                    template.id, template.name, user.username)
        return json_resp(ok({
            "template": serialize_template(template),
            "warnings": detect_template_overlap(template),
        }))

    def update(self, request, *args, **kwargs):
        user, resp = authed_user(request)
        if resp:
            return resp
        perr = _require_admin(user)
        if perr:
            return perr
        template = self.get_queryset().filter(pk=kwargs.get("pk")).first()
        if template is None:
            return fail_resp(40401, "时段模板不存在")
        serializer = SlotTemplateSerializer(template, data=request.data or {}, partial=True)
        if not serializer.is_valid():
            return fail_resp(42201, first_error(serializer.errors))
        template = serializer.save()
        logger.info("[slot-booking] template update id=%s actor=%s", template.id, user.username)
        return json_resp(ok({
            "template": serialize_template(template),
            "warnings": detect_template_overlap(template),
        }))

    def destroy(self, request, *args, **kwargs):
        user, resp = authed_user(request)
        if resp:
            return resp
        perr = _require_admin(user)
        if perr:
            return perr
        template = self.get_queryset().filter(pk=kwargs.get("pk")).first()
        if template is None:
            return fail_resp(40401, "时段模板不存在")
        if SlotBooking.objects.filter(template=template).exists():
            return fail_resp(40902, "该时段已有抢占记录，请改用停用")
        template.delete()
        logger.info("[slot-booking] template delete id=%s actor=%s", kwargs.get("pk"), user.username)
        return json_resp(ok(message="时段模板已删除"))


class SlotBookingViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """抢占记录：创建（全员）/ 释放 / 我的（分页）/ 全部（admin 筛选分页）。"""

    queryset = SlotBooking.objects.select_related("user", "version", "branch", "template")
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        user, resp = authed_user(request)
        if resp:
            return resp
        serializer = SlotBookingCreateSerializer(data=request.data or {})
        if not serializer.is_valid():
            return fail_resp(42201, first_error(serializer.errors))
        data, error = create_booking(user, serializer.validated_data)
        if error:
            return _err_resp(error)
        return json_resp(ok(data))

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        user, resp = authed_user(request)
        if resp:
            return resp
        booking = (
            self.get_queryset().filter(pk=pk).first()
        )
        if booking is None:
            return fail_resp(40401, "抢占记录不存在")
        serializer = ReleaseBookingSerializer(data=request.data or {})
        if not serializer.is_valid():
            return fail_resp(42201, first_error(serializer.errors))
        data, error = release_booking(booking, user, serializer.validated_data.get("release_reason", ""))
        if error:
            return _err_resp(error)
        return json_resp(ok(data))

    @action(detail=False, methods=["get"])
    def mine(self, request):
        user, resp = authed_user(request)
        if resp:
            return resp
        qs = self.get_queryset().filter(user=user).order_by("-date", "-id")
        return json_resp(ok(_paginate(qs, request, serialize_booking_row)))

    def list(self, request, *args, **kwargs):
        user, resp = authed_user(request)
        if resp:
            return resp
        perr = _require_admin(user)
        if perr:
            return perr
        qs = self.get_queryset().all()
        params = request.query_params
        try:
            if params.get("date_from"):
                qs = qs.filter(date__gte=params["date_from"])
            if params.get("date_to"):
                qs = qs.filter(date__lte=params["date_to"])
        except (ValueError, ValidationError):
            return fail_resp(42201, "日期筛选格式非法，应为 YYYY-MM-DD")
        if params.get("version_id"):
            qs = qs.filter(version_id=params["version_id"])
        if params.get("branch_id"):
            qs = qs.filter(branch_id=params["branch_id"])
        if params.get("user_id"):
            qs = qs.filter(user_id=params["user_id"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return json_resp(ok(_paginate(qs.order_by("-date", "-id"), request, serialize_booking_row)))


def slot_calendar(request):
    """月历聚合：GET /api/slot-calendar?month=YYYY-MM（缺省当月）。"""
    user, resp = authed_user(request)
    if resp:
        return resp
    month = request.GET.get("month") or timezone.localdate().strftime("%Y-%m")
    data, error = build_slot_calendar(month, user)
    if error:
        return _err_resp(error)
    return json_resp(ok(data))
