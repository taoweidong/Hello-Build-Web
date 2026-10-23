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


def _fmt_dt(value):
    """时间序列化：Asia/Shanghai 墙钟、不带 offset（R3-B3 统一口径）。

    与 views.fmt_dt 同语义；服务层不反向依赖视图层，故本地实现同款
    （此前直接对 aware UTC datetime strftime，输出早 8 小时，B-P1-3）。
    """
    if not value:
        return None
    if timezone.is_naive(value):
        return value.strftime(_FMT_DT)
    return timezone.localtime(value).strftime(_FMT_DT)


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
        "created_at": _fmt_dt(b.created_at),
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
        "created_at": _fmt_dt(b.created_at),
        "released_at": _fmt_dt(b.released_at),
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
        # 全角数字前置硬化（R6-B11，parse_int/valid_hhmm 同款 isascii 口径）：
        # int("２０２６") 在 Python 合法返回 2026，isdigit/异常捕获拦不住
        if not (year_str.isascii() and year_str.isdigit()
                and mon_str.isascii() and mon_str.isdigit()):
            return None, _err(CODE_UNPROCESSABLE, "月份格式非法，应为 YYYY-MM")
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

def _raise_slot_conflict_or_reraise(exc: IntegrityError, target_date, template, verb: str):
    """按目标唯一约束转 40904 冲突错误；非本约束的 IntegrityError 原样抛出。

    R4-B8/B4-08：此前 create/reschedule 的 IntegrityError 兜底过宽——不区分
    约束一律 40904「被他人抢占」，撞 NOT NULL/外键失效/并发删除时用户收到
    误导性冲突提示。对齐 services.strategies._raise_conflict_or_reraise 范式：
    SQLite 的 IntegrityError 消息只含 表名.列名（UNIQUE constraint failed:
    build_protection_service_slotbooking.date, ...template_id）不含约束名，
    按字段组合匹配——SlotBooking 表唯一约束仅 uniq_slot_booking_active
    （date+template 的 reserved 部分唯一）一个，两字段组合可精确定位；
    兼容部分后端（如 Postgres）消息携带约束名的情况。

    命中目标约束返回 (40904 错误 dict, 占有人名)；否则 raise 原异常保留堆栈。
    """
    msg = str(exc)
    hit = "uniq_slot_booking_active" in msg or (
        "slotbooking.date" in msg and "slotbooking.template_id" in msg
    )
    if not hit:
        raise exc
    holder = SlotBooking.objects.filter(
        date=target_date, template=template, status="reserved"
    ).select_related("user").first()
    holder_name = display_name(holder.user) if holder else "他人"
    return _err(CODE_SLOT_CONFLICT, f"该时段{verb}被 {holder_name} 抢占，请刷新后选择其他时段"), holder_name


def create_booking(user, payload: dict) -> tuple[Optional[dict], Optional[dict]]:
    """抢占：校验链 → 落库；唯一约束兜底并发，冲突转 40904。

    注意：purpose 长度与版本/分支归属校验与 SlotBookingCreateSerializer 双写
    （服务层是唯一裁决点，序列化器仅为 API 路径提前拦截）；修改任一处校验
    语义时必须同步另一处（2026-10-12 质量评估 B-P2-21 记录在案）。
    """
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

    raw_purpose = payload.get("purpose")
    # 字段级类型守卫（R6-B4，create 与 reschedule 的 R5-B9 口径统一）：非 str
    # 一律 42201 拒绝——此前 create 路径 str() 强转会接受 int（API 路径经 CharField
    # 静默强转同病）并把 dict 存成 "{'a': 1}" repr 串垃圾数据。
    if not isinstance(raw_purpose, str):
        return None, _err(CODE_UNPROCESSABLE, "purpose 应为字符串")
    purpose = raw_purpose.strip()
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
    except IntegrityError as exc:
        # 仅目标约束转 40904，其余 IntegrityError 原样上抛（R4-B8）
        conflict_err, holder_name = _raise_slot_conflict_or_reraise(exc, d, template, "刚")
        logger.info(
            "[slot-booking] conflict date=%s template=%s actor=%s holder=%s",
            d, template.id, user.username, holder_name,
        )
        return None, conflict_err

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
    # 释放原因守卫（R6-B5）：服务层是「双写校验」的最终裁决点，API 路径经
    # ReleaseBookingSerializer（严格 CharField，R6-B4）提前拦截，直调路径在此
    # 兜底——非 str 拒绝 + 长度取模型真实 max_length（SQLite 放行超长，迁 PG
    # 即 DataError）。None 归一为 ""（本人释放原因可选语义不变）。
    if release_reason is None:
        release_reason = ""
    if not isinstance(release_reason, str):
        return None, _err(CODE_UNPROCESSABLE, "释放原因应为字符串")
    reason = release_reason.strip()
    if len(reason) > SlotBooking.release_reason.field.max_length:
        return None, _err(CODE_UNPROCESSABLE, "释放原因长度不能超过 200 字符")
    if not is_owner and not reason:
        return None, _err(CODE_UNPROCESSABLE, "管理员释放他人抢占需填写释放原因")
    released_at = timezone.now()
    # 条件 UPDATE 抢占（R3-B9，对齐借用审批/结论提交范式）：入口的 status 检查是
    # check-then-act，并发双释放此前均成功且后者覆盖 released_at/reason（B-P2-8）；
    # 现在仅 status 仍为 reserved 时更新，rowcount=0 按既有"非待占用状态"语义报错。
    updated = SlotBooking.objects.filter(id=booking.id, status="reserved").update(
        status="released", released_at=released_at, release_reason=reason,
    )
    if not updated:
        return None, _err(CODE_UNPROCESSABLE, "该记录不是待占用状态，无法释放")
    booking.status = "released"
    booking.released_at = released_at
    booking.release_reason = reason
    logger.info(
        "[slot-booking] release id=%s actor=%s owner=%s reason=%s",
        booking.id, actor.username, booking.user.username, reason,
    )
    return _booking_dict(booking, actor.id), None


# ---------- 改期（P2-R2） ----------

def _resolve_target(booking, payload) -> tuple[Optional[object], Optional[object], Optional[object], Optional[dict]]:
    """解析改期目标（日期 / 模板 / 用途），缺省字段沿用原值。

    返回 `(date, template, purpose, error)`；任一失败时其余为 None。
    """
    raw_date = payload.get("date")
    if raw_date is None or str(raw_date).strip() == "":
        target_date = booking.date
    else:
        try:
            target_date = date_cls.fromisoformat(str(raw_date).strip())
        except (ValueError, TypeError):
            return None, None, None, _err(CODE_UNPROCESSABLE, "日期格式非法，应为 YYYY-MM-DD")

    raw_template = payload.get("template_id")
    if raw_template is None or str(raw_template).strip() == "":
        template = booking.template
    else:
        template_id = _safe_int(raw_template)
        if template_id is None:
            return None, None, None, _err(CODE_UNPROCESSABLE, "template_id 应为整数")
        template = SlotTemplate.objects.filter(id=template_id).first()
        if template is None:
            return None, None, None, _err(CODE_NOT_FOUND, "时段模板不存在")

    raw_purpose = payload.get("purpose")
    # 字段级类型守卫（R5-B9，body_str/conclusion note 同款口径）：非 str 一律
    # 42201 拒绝——此前 str() 强转会把 {"a":1} 存成 "{'a': 1}" repr 串垃圾数据
    # （长度恰在 2~200 内即放行）；create 路径经序列化器 CharField 会拒绝非 str，
    # 同一资源两条写路径口径由此统一。缺省（None）沿用原值语义不变。
    if raw_purpose is None:
        purpose = booking.purpose
    elif not isinstance(raw_purpose, str):
        return None, None, None, _err(CODE_UNPROCESSABLE, "purpose 应为字符串")
    else:
        purpose = raw_purpose.strip()
    if not 2 <= len(purpose) <= 200:
        return None, None, None, _err(CODE_UNPROCESSABLE, "用途说明需 2~200 字")

    return target_date, template, purpose, None


def reschedule_booking(booking: SlotBooking, actor, payload: dict) -> tuple[Optional[dict], Optional[dict]]:
    """抢占改期：本人或 admin；仅 reserved 可改；目标必须通过与抢占同一套校验链。

    校验口径与 `create_booking` 保持一致（过去日期 / 可抢窗口 / 模板启用 / 适用星期与生效期 /
    用途长度），区别仅在于改期是 UPDATE 而非 INSERT：(date, template) 的 reserved 部分唯一
    约束仍然生效，撞车由 IntegrityError 转 40904（message 带占有人）。
    并发下用条件 UPDATE（status=reserved）保证「改期 vs 释放 vs 他人再抢」只有一方成功。
    """
    if booking.status != "reserved":
        return None, _err(CODE_UNPROCESSABLE, "该记录不是待占用状态，无法改期")
    is_owner = booking.user_id == actor.id
    is_admin = getattr(actor, "role", "") == "admin"
    if not (is_owner or is_admin):
        return None, _err(CODE_FORBIDDEN, "无权限执行该操作")

    target_date, template, purpose, error = _resolve_target(booking, payload)
    if error:
        return None, error

    today = _today()
    if target_date < today:
        return None, _err(CODE_UNPROCESSABLE, "不能改到过去日期")
    if target_date > today + timedelta(days=_horizon_days()):
        return None, _err(
            CODE_UNPROCESSABLE, f"超出可抢占窗口（最多提前 {_horizon_days()} 天）"
        )
    if not template.enabled:
        return None, _err(CODE_UNPROCESSABLE, "该时段模板已停用")
    if not template_applies_on(template, target_date):
        return None, _err(
            CODE_UNPROCESSABLE, "该日期不在此时段的适用范围（星期/生效期）内"
        )

    # 捕获必须在 atomic 外层：块内捕获会让连接进入「事务已损坏」状态，
    # 后续查询冒 TransactionManagementError（与 create_booking 同款结构）。
    try:
        with transaction.atomic():
            updated = SlotBooking.objects.filter(
                id=booking.id, status="reserved"
            ).update(
                date=target_date,
                template=template,
                start_snapshot=template.start_time,
                end_snapshot=template.end_time,
                purpose=purpose,
            )
    except IntegrityError as exc:
        # 仅目标约束转 40904，其余 IntegrityError 原样上抛（R4-B8）
        conflict_err, _holder = _raise_slot_conflict_or_reraise(
            exc, target_date, template, "已"
        )
        return None, conflict_err
    if not updated:
        return None, _err(CODE_UNPROCESSABLE, "该记录不是待占用状态，无法改期")

    booking.date = target_date
    booking.template = template
    booking.start_snapshot = template.start_time
    booking.end_snapshot = template.end_time
    booking.purpose = purpose
    logger.info(
        "[slot-booking] reschedule id=%s actor=%s date=%s template=%s",
        booking.id, actor.username, target_date, template.id,
    )
    return _booking_dict(booking, actor.id), None
