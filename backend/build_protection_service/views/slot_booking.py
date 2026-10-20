"""时段抢占视图：日历聚合 / 抢占 / 释放 / 改期 / 我的抢占。

认证与错误码约定同 reports 模块：ViewSet 置 AllowAny，authed_user 手动校验；
统一响应 {code, message, data}；抢占冲突 40904。

2026-10-20 页面精简：时段模板 CRUD（原 SlotTemplateViewSet，时段配置页消费）与
admin 全量记录列表（原 SlotBookingViewSet.list，时段配置记录面板消费）随页面下线
删除；模板数据仅经月历聚合只读曝光，写入面收敛到 seed / django-admin。
"""
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from ..api import ok
from ..errors import CODE_NOT_FOUND, CODE_UNPROCESSABLE
from ..models import SlotBooking
from ..serializers.slot_booking import (
    ReleaseBookingSerializer,
    SlotBookingCreateSerializer,
)
from ..services.slot_booking import (
    build_slot_calendar,
    create_booking,
    release_booking,
    reschedule_booking,
    serialize_booking_row,
)
from . import authed_user, fail_resp, first_error, json_resp, paginate_qs


class SlotBookingViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """抢占记录：创建（全员）/ 释放 / 改期 / 我的（分页）。"""

    queryset = SlotBooking.objects.select_related("user", "version", "branch", "template")
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "patch", "head", "options"]

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

    def partial_update(self, request, *args, **kwargs):
        """改期（P2-R2）：PATCH /slot-bookings/<pk>，本人或 admin；仅 reserved 可改。"""
        user, resp = authed_user(request)
        if resp:
            return resp
        booking = self.get_queryset().filter(pk=kwargs.get("pk")).first()
        if booking is None:
            return fail_resp(CODE_NOT_FOUND, "抢占记录不存在")
        # 非 dict 载荷归一为 {}（R4-B3/B4-03，R3-B2 同款）：数组/字符串等此前
        # 直塞服务层，payload.get 冒 AttributeError 变 500；归一后与空 body 同
        # 语义（缺省字段沿用原值的 no-op 改期）
        body = request.data if isinstance(request.data, dict) else {}
        data, error = reschedule_booking(booking, user, body)
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
