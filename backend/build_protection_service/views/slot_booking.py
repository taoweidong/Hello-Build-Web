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

from ..api import ok
from ..errors import CODE_DUPLICATE, CODE_NOT_FOUND, CODE_UNPROCESSABLE
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
from . import authed_user, fail_resp, first_error, json_resp, paginate_qs, parse_int, require_admin

logger = logging.getLogger("build_protection_service")

# 分页实现已提升为 views 包共享助手 paginate_qs（R3-B11 收敛，reports 同款复用）


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
        perr = require_admin(user, message="无权限执行该操作")
        if perr:
            return perr
        serializer = SlotTemplateSerializer(data=request.data or {})
        if not serializer.is_valid():
            return fail_resp(CODE_UNPROCESSABLE, first_error(serializer.errors))
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
        perr = require_admin(user, message="无权限执行该操作")
        if perr:
            return perr
        template = self.get_queryset().filter(pk=kwargs.get("pk")).first()
        if template is None:
            return fail_resp(CODE_NOT_FOUND, "时段模板不存在")
        serializer = SlotTemplateSerializer(template, data=request.data or {}, partial=True)
        if not serializer.is_valid():
            return fail_resp(CODE_UNPROCESSABLE, first_error(serializer.errors))
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
        perr = require_admin(user, message="无权限执行该操作")
        if perr:
            return perr
        template = self.get_queryset().filter(pk=kwargs.get("pk")).first()
        if template is None:
            return fail_resp(CODE_NOT_FOUND, "时段模板不存在")
        if SlotBooking.objects.filter(template=template).exists():
            return fail_resp(CODE_DUPLICATE, "该时段已有抢占记录，请改用停用")
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
            return fail_resp(CODE_UNPROCESSABLE, first_error(serializer.errors))
        data, error = create_booking(user, serializer.validated_data)
        if error:
            return fail_resp(error["code"], error["message"])
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
            return fail_resp(CODE_NOT_FOUND, "抢占记录不存在")
        serializer = ReleaseBookingSerializer(data=request.data or {})
        if not serializer.is_valid():
            return fail_resp(CODE_UNPROCESSABLE, first_error(serializer.errors))
        data, error = release_booking(booking, user, serializer.validated_data.get("release_reason", ""))
        if error:
            return fail_resp(error["code"], error["message"])
        return json_resp(ok(data))

    @action(detail=False, methods=["get"])
    def mine(self, request):
        user, resp = authed_user(request)
        if resp:
            return resp
        qs = self.get_queryset().filter(user=user).order_by("-date", "-id")
        return json_resp(ok(paginate_qs(qs, request, serialize_booking_row)))

    def list(self, request, *args, **kwargs):
        user, resp = authed_user(request)
        if resp:
            return resp
        perr = require_admin(user, message="无权限执行该操作")
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
            return fail_resp(CODE_UNPROCESSABLE, "日期筛选格式非法，应为 YYYY-MM-DD")
        # 整数过滤参数须过 parse_int，非法值返回 42201（避免 filter(version_id="abc") → 500）
        for key in ("version_id", "branch_id", "user_id"):
            raw = params.get(key)
            if raw:
                val = parse_int(raw)
                if val is None:
                    return fail_resp(CODE_UNPROCESSABLE, f"{key} 应为整数")
                qs = qs.filter(**{key: val})
        status = params.get("status")
        if status:
            # 值域校验：任意串静默空结果会让调用方误以为"无数据"
            if status not in ("reserved", "released"):
                return fail_resp(CODE_UNPROCESSABLE, "status 应为 reserved 或 released")
            qs = qs.filter(status=status)
        return json_resp(ok(paginate_qs(qs.order_by("-date", "-id"), request, serialize_booking_row)))


def slot_calendar(request):
    """月历聚合：GET /api/slot-calendar?month=YYYY-MM（缺省当月）。"""
    # 方法守卫（R3-B16）：读端点仅 GET
    if request.method != "GET":
        return fail_resp(CODE_UNPROCESSABLE, "不支持的请求方法")
    user, resp = authed_user(request)
    if resp:
        return resp
    month = request.GET.get("month") or timezone.localdate().strftime("%Y-%m")
    data, error = build_slot_calendar(month, user)
    if error:
        return fail_resp(error["code"], error["message"])
    return json_resp(ok(data))
