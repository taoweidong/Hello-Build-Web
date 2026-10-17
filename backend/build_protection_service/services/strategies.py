"""策略领域服务：互斥/冲突校验、创建与更新（PM 与 admin 两入口共用）。

写路径统一包 transaction.atomic；校验失败抛 StrategyValidationError，
由视图层转统一响应（code + message + extra 冲突详情）。

并发兜底（三层，见 specs/2026-10-11-strategy-concurrency-guard-design.md）：
1. settings 的 SQLite transaction_mode=IMMEDIATE 使「校验读→写入」串行；
2. Strategy 的 uniq_active_strategy_branch_time 条件唯一约束（DB 层）；
3. 本模块捕获 IntegrityError 转 40902，视图层映射 HTTP 409。
"""
from django.db import IntegrityError, transaction

from ..errors import CODE_ASSOCIATION, CODE_DUPLICATE, CODE_STAGE_CONFLICT, CODE_UNPROCESSABLE
from ..models import BorrowFlow, Strategy, StrategyChangeLog
from .config import get_config
from .conflict import detect_conflicts
from .mutex import check_build_mutex
from .timeline import build_timeline, valid_hhmm


class StrategyValidationError(Exception):
    """策略校验失败：code/message 对应统一响应契约，extra 附冲突详情。"""

    def __init__(self, code, message, extra=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra or {}


def _validate_name(name):
    """策略名必填：非字符串/空串/纯空白 → 42201；超长（>200）→ 42201。

    Strategy.name 为非空约束字段，缺校验时缺 name 的创建请求会以
    IntegrityError 形态冒到视图层变 500（见 2026-10-12 质量评估 B-P0-2）。
    长度上限取模型 max_length=200（R4-B10）：拒绝优于静默截断，SQLite
    宽容超长串，迁 Postgres 即 DataError → 500。
    """
    if not isinstance(name, str) or not name.strip():
        raise StrategyValidationError(CODE_UNPROCESSABLE, "策略名必填")
    name = name.strip()
    if len(name) > 200:
        raise StrategyValidationError(CODE_UNPROCESSABLE, "策略名长度不能超过 200 字符")
    return name


class SimpleNamespaceTpl:
    """detect_conflicts 只需模板的冒烟/分析时长，用轻量鸭子类型避免查询。"""

    def __init__(self, smoke, analysis):
        self.smoke_minutes = smoke
        self.analysis_minutes = analysis


def validate_strategy(branch, template, build_start_time, push_start_time,
                      push_mode="normal", exclude_id=None, ds=None,
                      check_conflicts=True):
    """互斥 + 阶段冲突校验；失败抛 StrategyValidationError（40901/40902）。

    check_conflicts=False 时只跑格式校验（HH:MM/push_mode），跳过互斥与
    阶段冲突检测——供 update_strategy 对「结果态为停用」的策略使用（R5-B1）：
    停用策略不占时段（uniq_active_strategy_branch_time 只约束 enabled=True），
    对其跑启用口径的冲突校验会误拦合法操作（停用策略连改名都被 40902 锁死、
    漂移冲突策略无法经 PATCH 停用止血）。重新启用时 toggle/update 会再次
    完整校验，故停用态放行无实害。
    """
    from django.conf import settings
    from django.utils import timezone

    if not valid_hhmm(build_start_time):
        # build_start_time 为必填非空字段：此前 None 会跳过校验、落库时
        # IntegrityError 冒成 500（2026-10-12 评估 B-P1-12）
        raise StrategyValidationError(CODE_UNPROCESSABLE, "build_start_time 格式应为 HH:MM（0-23 时 0-59 分）")
    if push_start_time is not None and not valid_hhmm(push_start_time):
        raise StrategyValidationError(CODE_UNPROCESSABLE, "push_start_time 格式应为 HH:MM（0-23 时 0-59 分）")
    if push_mode not in ("normal", "sync"):
        # choices 仅在 full_clean 生效，直接 save 不校验；此处兜底防止
        # "xyz" 之类值静默入库导致时间线推导行为漂移
        raise StrategyValidationError(CODE_UNPROCESSABLE, "push_mode 应为 normal 或 sync")
    if not check_conflicts:
        return
    build_minutes = get_config("build_minutes", settings.BUILD_MINUTES)
    push_minutes = get_config("push_minutes", settings.PUSH_MINUTES)
    sync_buffer_minutes = get_config("sync_buffer_minutes", settings.SYNC_BUFFER_MINUTES)
    if ds is None:
        ds = timezone.localdate().strftime("%Y-%m-%d")

    mutex_hits = check_build_mutex(branch.version_id, build_start_time, build_minutes,
                                   exclude_strategy_id=exclude_id, ds=ds)
    if mutex_hits:
        raise StrategyValidationError(CODE_DUPLICATE, "同一时间节点仅允许一个分支构建（资源互斥）", extra={"mutex": mutex_hits})

    # select_related("template")：下方推导式逐条读 s.template.*，避免 N+1
    # （preview 是前端表单防抖高频路径，务必一次取全）
    same_branch = Strategy.objects.filter(branch=branch, enabled=True).select_related("template")
    if exclude_id:
        same_branch = same_branch.exclude(id=exclude_id)
    existing = [{
        "build_start_time": s.build_start_time,
        "template": SimpleNamespaceTpl(s.template.smoke_minutes, s.template.analysis_minutes),
        "push_mode": s.push_mode,
        "strategy_name": s.name,
        "push_start_time": s.push_start_time,
    } for s in same_branch]
    cand = [{
        "build_start_time": build_start_time,
        "template": SimpleNamespaceTpl(template.smoke_minutes, template.analysis_minutes),
        "push_mode": push_mode,
        "strategy_name": "candidate",
        "push_start_time": push_start_time,
    }]
    hits = detect_conflicts(ds, cand, existing, build_minutes, push_minutes, sync_buffer_minutes)
    if hits:
        raise StrategyValidationError(CODE_STAGE_CONFLICT, "阶段时间冲突，请调整构建时间", extra={"conflicts": hits})


def strategy_payload(s: Strategy) -> dict:
    """策略统一输出契约（列表/详情/创建/更新共用）。"""
    return {
        "id": s.id,
        "branch_id": s.branch_id,
        "branch_name": s.branch.name,
        "version_id": s.branch.version_id,
        "version_name": s.branch.version.name,
        "template_id": s.template_id,
        "template_name": s.template.name,
        "name": s.name,
        "build_start_time": s.build_start_time,
        "push_start_time": s.push_start_time,
        "push_mode": s.push_mode,
        "enabled": s.enabled,
    }


# 可变字段 → 变更日志中文标签
_CHANGE_LABELS = {
    "name": "策略名",
    "build_start_time": "构建开始时间",
    "push_start_time": "推送开始时间",
    "push_mode": "推送模式",
    "enabled": "启用",
}


def _change_desc(old: dict, body: dict) -> str:
    """按请求体实际改动字段生成变更描述，如「构建开始时间: 22:00→23:00」。"""
    parts = []
    for field, label in _CHANGE_LABELS.items():
        if body.get(field) is None:
            continue
        new_val = body[field]
        if field == "push_start_time" and not new_val:
            new_val = None
        if old.get(field) != new_val:
            parts.append(f"{label}: {old.get(field)}→{new_val}")
    return "；".join(parts)


@transaction.atomic
def create_strategy(branch, template, operator, *, name, build_start_time,
                    push_start_time=None, push_mode="normal", enabled=True):
    """创建策略（含校验），供 PM 与 admin 两入口共用。

    校验竞态兜底：并发下另一事务可能在校验读之后、本事务写之前提交冲突策略，
    唯一约束 uniq_active_strategy_branch_time 在 DB 层拦截，转 40902。
    """
    name = _validate_name(name)
    if not isinstance(enabled, bool):
        raise StrategyValidationError(CODE_UNPROCESSABLE, "enabled 应为布尔值")
    validate_strategy(branch, template, build_start_time, push_start_time, push_mode=push_mode)
    try:
        return Strategy.objects.create(
            branch=branch, template=template, name=name,
            build_start_time=build_start_time,
            push_start_time=push_start_time or None,
            push_mode=push_mode, enabled=enabled, created_by=operator,
        )
    except IntegrityError as exc:
        _raise_conflict_or_reraise(exc, branch, build_start_time)


@transaction.atomic
def update_strategy(strategy: Strategy, body: dict, operator):
    """按请求体增量更新策略并留痕字段差异；校验失败抛 StrategyValidationError。"""
    old = strategy_payload(strategy)
    build_start_time = body.get("build_start_time", strategy.build_start_time)
    push_start_time = body.get("push_start_time", strategy.push_start_time)
    push_mode = strategy.push_mode if body.get("push_mode") is None else body["push_mode"]
    enabled = strategy.enabled if body.get("enabled") is None else body["enabled"]
    if not isinstance(enabled, bool):
        raise StrategyValidationError(CODE_UNPROCESSABLE, "enabled 应为布尔值")
    # R5-B1：冲突校验仅在结果态为启用时执行（对齐 toggle_strategy 的
    # 「仅启用方向校验」语义）；格式校验（HH:MM/push_mode）恒跑。
    validate_strategy(strategy.branch, strategy.template, build_start_time, push_start_time,
                      push_mode=push_mode, exclude_id=strategy.id,
                      check_conflicts=enabled)
    if body.get("name") is not None:
        strategy.name = _validate_name(body["name"])
    strategy.build_start_time = build_start_time
    strategy.push_start_time = push_start_time or None
    strategy.push_mode = push_mode
    strategy.enabled = enabled
    try:
        strategy.save()
    except IntegrityError as exc:
        _raise_conflict_or_reraise(exc, strategy.branch, build_start_time)
    desc = _change_desc(old, body)
    StrategyChangeLog.objects.create(
        strategy=strategy, operator=operator,
        change_desc=(f"更新策略: {old['name']}（{desc}）" if desc else f"更新策略: {old['name']}")[:255],
    )
    return strategy


@transaction.atomic
def toggle_strategy(strategy: Strategy) -> Strategy:
    """启停策略（R3-B4）：启用方向先跑统一校验，落库用条件 UPDATE 防并发。

    审计留痕由调用方负责：PM 入口写 StrategyChangeLog、admin 入口写
    AdminOpLog（双轨口径不变，见 views 层）。

    此前 toggle 是唯一未套「条件 UPDATE 抢占」范式的写路径（读改写竞态 +
    重新启用绕过互斥/阶段校验，2026-10-13 评估 B-P2-1）：
    - 启用方向（False→True）：先跑 validate_strategy（资源互斥 40902 /
      阶段冲突 40901 / 参数非法 42201），杜绝"停用 A → 他分支建同刻 B →
      重新启用 A"静默生效；
    - 条件 UPDATE filter(id, enabled=旧值)：rowcount=0 说明并发已被他人翻转
      或字段被并发修改 → 抛 40902，消除丢翻转与旧快照覆盖；
    - IntegrityError → 40902 兜底保留（校验读与 UPDATE 之间的真并发窗口撞
      uniq_active_strategy_branch_time 约束）。
    """
    old_enabled = strategy.enabled
    new_enabled = not old_enabled
    if new_enabled:
        validate_strategy(
            strategy.branch, strategy.template,
            strategy.build_start_time, strategy.push_start_time,
            push_mode=strategy.push_mode, exclude_id=strategy.id,
        )
    try:
        updated = Strategy.objects.filter(
            id=strategy.id, enabled=old_enabled
        ).update(enabled=new_enabled)
    except IntegrityError as exc:
        _raise_conflict_or_reraise(exc, strategy.branch, strategy.build_start_time)
    if not updated:
        raise StrategyValidationError(
            CODE_DUPLICATE, "策略状态已被其他操作修改，请刷新后重试"
        )
    strategy.enabled = new_enabled
    return strategy


@transaction.atomic
def delete_strategy(strategy: Strategy) -> None:
    """删除策略（R4-B1，PM 与 admin 两入口共用）：事务内拦截 pending 借用流。

    BorrowFlow.strategy 为 CASCADE，直接删除会静默抹掉进行中的待审批电子流
    （借用人/审批人无感知）与全部 ExecutionRound 历史；此前仅 PM 入口有拦截
    （R3-B5），admin 入口反而约束更松（2026-10-15 评估 B4-01）。检查与删除
    同一事务（SQLite IMMEDIATE 串行化写路径），防检查后插入。

    拦截时抛 StrategyValidationError（40903，复用既有「存在待审批借用流」文案）；
    审计留痕由调用方负责：PM 入口在同事务内写 AdminOpLog、admin 入口写
    AdminOpLog（StrategyChangeLog 随策略级联删除，不能承载删除审计，R3-B5）。
    """
    if BorrowFlow.objects.filter(strategy=strategy, status="pending").exists():
        raise StrategyValidationError(
            CODE_ASSOCIATION, "存在待审批的借用申请，请先处理后再删除"
        )
    strategy.delete()


def _raise_conflict_or_reraise(exc: IntegrityError, branch, build_start_time):
    """按唯一约束语义转 40902；非本约束的 IntegrityError 原样抛出。

    消息匹配双格式（R5-B2，对齐 slot_booking 版 R4-B8）：
    - SQLite 只含字段名（UNIQUE constraint failed: ...branch_id,
      build_start_time），按字段组合匹配（Strategy 表唯一约束仅此一个，
      两字段组合可精确定位）；
    - Postgres 等后端消息携带约束名（duplicate key value violates unique
      constraint "uniq_active_strategy_branch_time"），按约束名匹配——迁 PG
      后这层 DB 兜底是并发撞约束的唯一防线，勿再引入单格式匹配。
    """
    msg = str(exc)
    if "uniq_active_strategy_branch_time" in msg or (
        "strategy.branch_id" in msg and "build_start_time" in msg
    ):
        raise StrategyValidationError(
            CODE_DUPLICATE,
            f"该分支已存在 {build_start_time} 开始的启用策略（并发提交冲突，请刷新后重试）",
        ) from exc
    raise exc
