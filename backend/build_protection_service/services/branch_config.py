"""分支配置服务：角色解析、实例状态机模拟、聚合配置组装。

纯模拟约定：
- start 创建 STARTING 实例（随机 pid 32000-49999）；
- STARTING 距 started_at 超过 START_READY_SECONDS 秒后，在下一次读取时被推进为 RUNNING；
- stop 仅对 STARTING/RUNNING 生效，置 STOPPED 并记录 stopped_at/exit_code=0；
- ERROR 状态本期仅保留枚举，不做自动判定。
"""
import json
import logging
import random
from typing import Dict, List, Optional

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from ..models import Branch, BranchPermission, BranchProject, Instance, Project, StartupConfig

logger = logging.getLogger("build_protection_service")

User = get_user_model()

ROLE_VIEWER = "VIEWER"
ROLE_OPERATOR = "OPERATOR"
ROLE_ADMIN = "ADMIN"
ROLE_VALID = (ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN)

START_READY_SECONDS = 2
_FMT = "%Y-%m-%dT%H:%M:%S"


# ---------- 角色解析 ----------

def resolve_role(branch: Branch, user) -> str:
    """计算用户对分支的有效角色：系统 admin 恒为 ADMIN，无授权默认 VIEWER。"""
    if getattr(user, "role", "") == "admin":
        return ROLE_ADMIN
    perm = BranchPermission.objects.filter(branch=branch, user=user).first()
    return perm.role if perm else ROLE_VIEWER


# ---------- 实例状态机 ----------

def advance(instance: Instance) -> None:
    """按时间推进：STARTING 超阈值 → RUNNING；RUNNING 刷新心跳。"""
    now = timezone.now()
    if instance.status == "STARTING" and instance.started_at:
        if (now - instance.started_at).total_seconds() > START_READY_SECONDS:
            instance.status = "RUNNING"
            instance.last_heartbeat_at = now
            instance.save(update_fields=["status", "last_heartbeat_at", "updated_at"])
            return
    if instance.status == "RUNNING":
        instance.last_heartbeat_at = now
        instance.save(update_fields=["last_heartbeat_at", "updated_at"])


def start_instance(branch_project: BranchProject, actor: str) -> Optional[Instance]:
    """启动模拟：存在运行中实例返回 None（由视图层转 40903），否则创建 STARTING。

    事务 + 活跃实例部分唯一约束兜底并发启动：竞态命中约束按"已在运行"处理。
    """
    try:
        with transaction.atomic():
            running = Instance.objects.filter(
                branch_project=branch_project, status__in=("STARTING", "RUNNING")
            ).exists()
            if running:
                return None
            now = timezone.now()
            pid = random.randint(32000, 49999)
            inst = Instance.objects.create(
                branch_project=branch_project,
                status="STARTING",
                pid=pid,
                started_at=now,
                last_heartbeat_at=now,
                log_tail=f"[{actor}] 发起启动 pid={pid}",
            )
    except IntegrityError:
        logger.info(
            "[branch-instance][simulate] start bp=%s 并发命中唯一约束，按已在运行处理",
            branch_project.id,
        )
        return None
    logger.info(
        "[branch-instance][simulate] start bp=%s pid=%s actor=%s",
        branch_project.id, pid, actor,
    )
    return inst


def stop_instance(branch_project: BranchProject, actor: str) -> Optional[Instance]:
    """停止模拟：仅 STARTING/RUNNING 生效；无实例或已停止幂等返回当前实例。

    条件 UPDATE（R4-B16/B4-16，对齐 R3-B9 release_booking 范式）：此前读改写
    无条件 save，并发双 stop 均成功且后者覆盖 stopped_at/log_tail；现在仅
    status 仍为 STARTING/RUNNING 时更新，rowcount=0 说明并发窗口内已被他人
    停止，重读当前状态幂等返回（不覆盖首次停止的 stopped_at/log_tail）。
    """
    inst = Instance.objects.filter(branch_project=branch_project).order_by("-id").first()
    if inst is None or inst.status not in ("STARTING", "RUNNING"):
        return inst
    now = timezone.now()
    log_tail = (inst.log_tail + f"\n[{actor}] 发起停止").strip()
    # updated_at 为 auto_now 字段，queryset.update 不触发 pre_save，需显式写入
    updated = Instance.objects.filter(
        id=inst.id, status__in=("STARTING", "RUNNING")
    ).update(status="STOPPED", stopped_at=now, exit_code=0, log_tail=log_tail, updated_at=now)
    if not updated:
        # 并发窗口内已被他人停止：重读返回当前实例（幂等语义不变）
        inst.refresh_from_db()
        return inst
    inst.status = "STOPPED"
    inst.stopped_at = now
    inst.exit_code = 0
    inst.log_tail = log_tail
    logger.info(
        "[branch-instance][simulate] stop bp=%s pid=%s actor=%s",
        branch_project.id, inst.pid, actor,
    )
    return inst


def latest_instances_for_branch(branch: Branch) -> Dict[int, Instance]:
    """单查询批量取分支下全部关联的最新实例，消除逐关联 N+1。"""
    latest_id = Instance.objects.filter(
        branch_project_id=OuterRef("branch_project_id")
    ).order_by("-id").values("id")[:1]
    rows = Instance.objects.filter(
        branch_project__branch=branch, id=Subquery(latest_id)
    )
    return {row.branch_project_id: row for row in rows}


# ---------- 序列化辅助 ----------

def _dt(value) -> Optional[str]:
    """时间序列化：Asia/Shanghai 墙钟、不带 offset（R3-B3 统一口径）。

    此前直接对 aware UTC datetime strftime，输出早 8 小时（B-P1-3）；
    naive 值防御性按墙钟直出（USE_TZ=True 下 DB 读出恒为 aware）。
    """
    if not value:
        return None
    if timezone.is_naive(value):
        return value.strftime(_FMT)
    return timezone.localtime(value).strftime(_FMT)


def serialize_instance(inst: Instance) -> Dict:
    return {
        "id": inst.id,
        "status": inst.status,
        "pid": inst.pid,
        "started_at": _dt(inst.started_at),
        "stopped_at": _dt(inst.stopped_at),
        "last_heartbeat_at": _dt(inst.last_heartbeat_at),
        "exit_code": inst.exit_code,
        "log_tail": inst.log_tail,
    }


def serialize_config(conf: StartupConfig) -> Dict:
    return {
        "command": conf.command,
        "args": conf.args,
        "env_vars": conf.env_vars,
        "working_directory": conf.working_directory,
        "timeout_seconds": conf.timeout_seconds,
        "auto_restart": conf.auto_restart,
        "raw_json": conf.raw_json,
        "updated_at": _dt(conf.updated_at),
    }


def serialize_branch(branch: Branch) -> Dict:
    return {
        "id": branch.id,
        "version_id": branch.version_id,
        "version_name": branch.version.name,
        "name": branch.name,
        "repository_url": branch.repository_url,
        "description": branch.description,
    }


def serialize_project(project: Project) -> Dict:
    return {
        "id": project.id,
        "name": project.name,
        "repository_url": project.repository_url,
        "description": project.description,
    }


# ---------- 聚合配置 ----------

def build_branch_config(branch: Branch, user) -> Dict:
    """组装聚合配置：分支 + 工程关联（含启动配置与最新实例）+ 授权 + 可用用户/工程。"""
    items: List[Dict] = []
    bps = branch.branch_projects.select_related("project", "startup_config").all()
    latest_by_bp = latest_instances_for_branch(branch)
    for bp in bps:
        adv = latest_by_bp.get(bp.id)
        if adv:
            advance(adv)
        conf = getattr(bp, "startup_config", None)
        items.append(
            {
                "id": bp.id,
                "enabled": bp.enabled,
                "project": serialize_project(bp.project),
                "startup_config": serialize_config(conf) if conf else None,
                "latest_instance": serialize_instance(adv) if adv else None,
            }
        )
    perms = BranchPermission.objects.filter(branch=branch).select_related("user").order_by("id")
    return {
        "branch": serialize_branch(branch),
        "branch_projects": items,
        "permissions": [
            {"id": p.id, "user_id": p.user_id, "username": p.user.username, "role": p.role}
            for p in perms
        ],
        "my_role": resolve_role(branch, user),
        "available_users": [
            {"id": u.id, "username": u.username, "role": u.role}
            for u in User.objects.filter(is_active=True).order_by("id")
        ],
        "available_projects": [
            {"id": p.id, "name": p.name} for p in Project.objects.all().order_by("id")
        ],
    }


def dump_raw_config(conf: StartupConfig) -> str:
    """生成 raw_json 原始配置 JSON（供序列化器写入）。"""
    return json.dumps(
        {
            "command": conf.command,
            "args": conf.args,
            "env_vars": conf.env_vars,
            "working_directory": conf.working_directory,
            "timeout_seconds": conf.timeout_seconds,
            "auto_restart": conf.auto_restart,
        },
        ensure_ascii=False,
    )