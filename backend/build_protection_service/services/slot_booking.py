"""时段抢占服务：月历聚合、抢占事务、释放、模板重叠检测、惰性过期。

约定：
- 过期采用惰性标记：date < today 的 reserved 记录按 expired 展示，不落定时任务；
- 抢占落库时复制模板起止时间（快照），模板后续改动不影响历史抢占；
- 并发双抢由 partial unique 约束兜底，IntegrityError 转 40904（message 带占有人）。
"""
import logging
from datetime import date as date_cls
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import Branch, SlotBooking, SlotTemplate, Version
from ..errors import CODE_FORBIDDEN, CODE_NOT_FOUND, CODE_SLOT_CONFLICT, CODE_UNPROCESSABLE
# 整数解析与视图层同一实现（原 _safe_int 与 views.parse_int 逐字符相同的双份收敛）
from ..parsing import parse_int as _safe_int

logger = logging.getLogger("build_protection_service")

_FMT_DT = "%Y-%m-%dT%H:%M:%S"


def _err(code: int, message: str) -> dict:
    return {"code": code, "message": message}


def _today() -> date_cls:
    return timezone.localdate()


def _horizon_days() -> int:
    return int(getattr(settings, "SLOT_BOOKING_HORIZON_DAYS", 60))


def _weekdays_set(weekdays: str):
    """解析 "1,2,3" 为集合；空串表示每天（返回 None）。"""
    if not weekdays:
        return None
    return {w.strip() for w in weekdays.split(",") if w.strip()}


def template_applies_on(template: SlotTemplate, d: date_cls) -> bool:
    """模板在某天是否适用：启用 + 星期匹配 + 生效范围覆盖。"""
    if not template.enabled:
        return False
    wd = _weekdays_set(template.weekdays)
    if wd is not None and str(d.isoweekday()) not in wd:
        return False
    if template.effective_from and d < template.effective_from:
        return False
    if template.effective_to and d > template.effective_to:
        return False
    return True


def display_name(user) -> str:
    return getattr(user, "display_name", "") or user.username


# ---------- 序列化 ----------

def serialize_template(t: SlotTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "start_time": t.start_time.strftime("%H:%M"),
        "end_time": t.end_time.strftime("%H:%M"),
        "weekdays": t.weekdays or "",
        "effective_from": t.effective_from.isoformat() if t.effective_from else None,
        "effective_to": t.effective_to.isoformat() if t.effective_to else None,
        "color": t.color,
        "sort_order": t.sort_order,
        "enabled": t.enabled,
    }


def _booking_dict(b: SlotBooking, viewer_id) -> dict:
    return {
        "id": b.id,
        "status": b.status,
        "user_name": display_name(b.user),
        "purpose": b.purpose,
        "version_id": b.version_id,
        "version_name": b.version.name,
        "branch_id": b.branch_id,
        "branch_name": b.branch.name,
        "is_mine": b.user_id == viewer_id,
        "created_at": b.created_at.strftime(_FMT_DT) if b.created_at else None,
    }


def serialize_booking_row(b: SlotBooking) -> dict:
    """抢占记录列表行（我的抢占 / admin 记录列表）。"""
    return {
        "id": b.id,
        "date": b.date.isoformat(),
        "template_id": b.template_id,
        "template_name": b.template.name,
        "start_time": b.start_snapshot.strftime("%H:%M"),
        "end_time": b.end_snapshot.strftime("%H:%M"),
        "status": b.status,
        "purpose": b.purpose,
        "version_id": b.version_id,
        "version_name": b.version.name,
        "branch_id": b.branch_id,
        "branch_name": b.branch.name,
        "user_id": b.user_id,
        "user_name": display_name(b.user),
        "created_at": b.created_at.strftime(_FMT_DT) if b.created_at else None,
        "released_at": b.released_at.strftime(_FMT_DT) if b.released_at else None,
        "release_reason": b.release_reason,
    }


# ---------- 月历聚合 ----------

def build_slot_calendar(month: str, user) -> tuple[Optional[dict], Optional[dict]]:
    """单次聚合整月状态矩阵：{month, horizon_days, templates, days}。

    days 仅包含存在适用模板的日期；每条目 {template_id, status, booking}，
    status ∈ available / reserved；过期（date < today）由前端按日期置灰。
    """
    try:
        year_str, mon_str = str(month).strip().split("-")
        first = date_cls(int(year_str), int(mon_str), 1)
    except (ValueError, TypeError):
        return None, _err(CODE_UNPROCESSABLE, "月份格式非法，应为 YYYY-MM")
    if first.month == 12:
        last = first.replace(day=31)
    else:
        last = date_cls(first.year, first.month + 1, 1) - timedelta(days=1)

    today = _today()
    templates = sorted(
        SlotTemplate.objects.filter(enabled=True), key=lambda t: (t.sort_order, t.id)
    )
    booking_map = {
        (b.date, b.template_id): b
        for b in SlotBooking.objects.filter(
            date__gte=first, date__lte=last, status="reserved"
        ).select_related("user", "version", "branch", "template")
    }

    days: dict[str, list] = {}
    d = first
    while d <= last:
        entries = []
        for t in templates:
            if not template_applies_on(t, d):
                continue
            b = booking_map.get((d, t.id))
            if b is not None:
                entries.append(
                    {"template_id": t.id, "status": "reserved",
                     "booking": _booking_dict(b, user.id)}
                )
            else:
                entries.append({"template_id": t.id, "status": "available", "booking": None})
        if entries:
            days[d.isoformat()] = entries
        d += timedelta(days=1)

    return {
        "month": f"{first.year:04d}-{first.month:02d}",
        "horizon_days": _horizon_days(),
        "templates": [serialize_template(t) for t in templates],
        "days": days,
    }, None


# ---------- 抢占 ----------

def create_booking(user, payload: dict) -> tuple[Optional[dict], Optional[dict]]:
    """抢占：校验链 → 落库；唯一约束兜底并发，冲突转 40904。"""
    try:
        d = date_cls.fromisoformat(str(payload.get("date") or "").strip())
    except ValueError:
        return None, _err(CODE_UNPROCESSABLE, "日期格式非法，应为 YYYY-MM-DD")

    template_id = _safe_int(payload.get("template_id"))
    if template_id is None:
        return None, _err(CODE_UNPROCESSABLE, "template_id 应为整数")
    template = SlotTemplate.objects.filter(id=template_id).first()
    if template is None:
        return None, _err(CODE_NOT_FOUND, "时段模板不存在")
    if not template.enabled:
        return None, _err(CODE_UNPROCESSABLE, "该时段模板已停用")

    today = _today()
    if d < today:
        return None, _err(CODE_UNPROCESSABLE, "不能抢占过去日期")
    if d > today + timedelta(days=_horizon_days()):
        return None, _err(CODE_UNPROCESSABLE, f"超出可抢占窗口（最多提前 {_horizon_days()} 天）")
    if not template_applies_on(template, d):
        return None, _err(CODE_UNPROCESSABLE, "该日期不在此时段的适用范围（星期/生效期）内")

    purpose = str(payload.get("purpose") or "").strip()
    if not 2 <= len(purpose) <= 200:
        return None, _err(CODE_UNPROCESSABLE, "用途说明需 2~200 字")

    version_id = _safe_int(payload.get("version_id"))
    branch_id = _safe_int(payload.get("branch_id"))
    if version_id is None or branch_id is None:
        return None, _err(CODE_UNPROCESSABLE, "version_id / branch_id 应为整数")
    version = Version.objects.filter(id=version_id).first()
    branch = Branch.objects.select_related("version").filter(id=branch_id).first()
    if version is None or branch is None:
        return None, _err(CODE_UNPROCESSABLE, "版本或分支不存在")
    if branch.version_id != version.id:
        return None, _err(CODE_UNPROCESSABLE, "分支不属于所选版本")

    try:
        with transaction.atomic():
            booking = SlotBooking.objects.create(
                date=d,
                template=template,
                start_snapshot=template.start_time,
                end_snapshot=template.end_time,
                status="reserved",
                user=user,
                purpose=purpose,
                version=version,
                branch=branch,
            )
    except IntegrityError:
        holder = SlotBooking.objects.filter(
            date=d, template=template, status="reserved"
        ).select_related("user").first()
        holder_name = display_name(holder.user) if holder else "他人"
        logger.info(
            "[slot-booking] conflict date=%s template=%s actor=%s holder=%s",
            d, template.id, user.username, holder_name,
        )
        return None, _err(CODE_SLOT_CONFLICT, f"该时段刚被 {holder_name} 抢占，请刷新后选择其他时段")

    logger.info(
        "[slot-booking] create id=%s date=%s template=%s actor=%s",
        booking.id, d, template.name, user.username,
    )
    return _booking_dict(booking, user.id), None


# ---------- 释放 ----------

def release_booking(booking: SlotBooking, actor, release_reason: str) -> tuple[Optional[dict], Optional[dict]]:
    """释放抢占：本人可释（原因可选）；admin 释他人必须填原因。"""
    if booking.status != "reserved":
        return None, _err(CODE_UNPROCESSABLE, "该记录不是待占用状态，无法释放")
    is_owner = booking.user_id == actor.id
    is_admin = getattr(actor, "role", "") == "admin"
    if not (is_owner or is_admin):
        return None, _err(CODE_FORBIDDEN, "无权限执行该操作")
    reason = str(release_reason or "").strip()
    if not is_owner and not reason:
        return None, _err(CODE_UNPROCESSABLE, "管理员释放他人抢占需填写释放原因")
    booking.status = "released"
    booking.released_at = timezone.now()
    booking.release_reason = reason
    booking.save(update_fields=["status", "released_at", "release_reason"])
    logger.info(
        "[slot-booking] release id=%s actor=%s owner=%s reason=%s",
        booking.id, actor.username, booking.user.username, reason,
    )
    return _booking_dict(booking, actor.id), None


# ---------- 模板重叠检测 ----------

def detect_template_overlap(template: SlotTemplate) -> list[str]:
    """同星期下与其他启用模板的时间区间重叠告警（允许保存，仅提示）。"""
    warnings: list[str] = []
    my_wd = _weekdays_set(template.weekdays)
    others = SlotTemplate.objects.filter(enabled=True).exclude(id=template.id)
    for other in others:
        other_wd = _weekdays_set(other.weekdays)
        if my_wd is not None and other_wd is not None and not (my_wd & other_wd):
            continue
        if template.start_time < other.end_time and other.start_time < template.end_time:
            warnings.append(
                f"与「{other.name}」"
                f"（{other.start_time:%H:%M}-{other.end_time:%H:%M}）时间重叠"
            )
    return warnings
