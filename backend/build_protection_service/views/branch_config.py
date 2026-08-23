"""分支配置视图：分支/工程关联/授权/实例（DRF ViewSet + action，聚合服务层组装）。

认证与错误码约定同 reports 模块：ViewSet 置 AllowAny，authed_user 手动校验；
统一响应 {code, message, data}；重名用 40902，重复关联/授权/启动用 40903。
"""
import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from ..api import err, ok
from ..models import (
    Branch,
    BranchPermission,
    BranchProject,
    Project,
    StartupConfig,
    Version,
)
from ..serializers.branch_config import StartupConfigSerializer
from ..services.branch_config import (
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_VALID,
    advance,
    build_branch_config,
    latest_instance,
    resolve_role,
    serialize_branch,
    serialize_config,
    serialize_instance,
    serialize_project,
    start_instance as svc_start,
    stop_instance as svc_stop,
)
from . import authed_user, json_resp, parse_body

logger = logging.getLogger("build_protection_service")

User = get_user_model()


def _first_error(errors: dict) -> str:
    """取 serializer 错误第一条消息用于统一提示。"""
    for value in errors.values():
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, str) and value:
            return value
    return "参数校验失败"


def _branch_or_none(pk) -> Branch:
    return Branch.objects.select_related("version").filter(pk=pk).first()


def _bp_or_none(pk) -> BranchProject:
    return BranchProject.objects.select_related("project", "branch__version").filter(pk=pk).first()


def _branch_required(branch):
    """分支不存在返回 (None, 404 响应)。"""
    if branch is None:
        return None, json_resp(err(40401, "分支不存在"), status=404)
    return branch, None


def _bp_required(bp):
    if bp is None:
        return None, json_resp(err(40401, "工程关联不存在"), status=404)
    return bp, None


def _require_role(user, branch, *roles):
    """角色门槛：有效角色不在 roles 内则返回 40301 响应。"""
    if resolve_role(branch, user) not in roles:
        return json_resp(err(40301, "无权限执行该操作"), status=403)
    return None


def _serialize_perm(perm) -> dict:
    return {
        "id": perm.id,
        "user_id": perm.user_id,
        "username": perm.user.username,
        "role": perm.role,
    }


class BranchViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """分支主视图：列表/创建/删除 + 聚合配置/添加工程/授权/实例轮询 action。"""

    queryset = Branch.objects.select_related("version").all()
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def list(self, request, *args, **kwargs):
        user, error = authed_user(request)
        if error:
            return error
        qs = self.get_queryset().order_by("version__id", "id")
        return json_resp(ok([serialize_branch(b) for b in qs]))

    def create(self, request, *args, **kwargs):
        user, error = authed_user(request)
        if error:
            return error
        body = request.data or {}
        version_id = body.get("version_id")
        version = Version.objects.filter(id=version_id).first() if version_id else None
        if version is None:
            return json_resp(err(42201, "版本必选且存在"), status=422)
        name = (body.get("name") or "").strip()
        if not name:
            return json_resp(err(42201, "分支名必填"), status=422)
        if Branch.objects.filter(version=version, name=name).exists():
            return json_resp(err(40902, "该版本下分支已存在"), status=409)
        try:
            branch = Branch.objects.create(
                version=version,
                name=name,
                repository_url=(body.get("repository_url") or "").strip(),
                description=(body.get("description") or "").strip(),
            )
        except IntegrityError:
            return json_resp(err(40902, "该版本下分支已存在"), status=409)
        return json_resp(ok(serialize_branch(branch)))

    def destroy(self, request, *args, **kwargs):
        user, error = authed_user(request)
        if error:
            return error
        branch, resp_err = _branch_required(_branch_or_none(kwargs.get("pk")))
        if resp_err:
            return resp_err
        perr = _require_role(user, branch, ROLE_ADMIN)
        if perr:
            return perr
        branch_name = f"{branch.version.name}/{branch.name}"
        branch.delete()  # 级联清理工程关联/启动配置/授权/实例
        logger.info("[branch-config] delete branch=%s actor=%s", branch_name, user.username)
        return json_resp(ok(message="分支已删除"))

    @action(detail=True, methods=["get"])
    def config(self, request, pk=None):
        user, error = authed_user(request)
        if error:
            return error
        branch, resp_err = _branch_required(_branch_or_none(pk))
        if resp_err:
            return resp_err
        return json_resp(ok(build_branch_config(branch, user)))

    @action(detail=True, methods=["post"])
    def projects(self, request, pk=None):
        """添加工程关联：ADMIN；重复关联 40903。"""
        user, error = authed_user(request)
        if error:
            return error
        branch, resp_err = _branch_required(_branch_or_none(pk))
        if resp_err:
            return resp_err
        perr = _require_role(user, branch, ROLE_ADMIN)
        if perr:
            return perr
        body = request.data or {}
        project = Project.objects.filter(id=body.get("project_id")).first()
        if project is None:
            return json_resp(err(42201, "工程不存在"), status=422)
        if BranchProject.objects.filter(branch=branch, project=project).exists():
            return json_resp(err(40903, "该工程已关联此分支"), status=409)
        bp = BranchProject.objects.create(
            branch=branch, project=project, enabled=bool(body.get("enabled", True))
        )
        # 关联创建默认启动配置，保证前端 Tab② 可编辑
        StartupConfig.objects.create(branch_project=bp)
        return json_resp(
            ok(
                {
                    "id": bp.id,
                    "enabled": bp.enabled,
                    "project": serialize_project(project),
                    "startup_config": None,
                    "latest_instance": None,
                }
            )
        )

    @action(detail=True, methods=["post"])
    def permissions(self, request, pk=None):
        """添加/更新授权（幂等 upsert）：ADMIN；角色非法 42201。"""
        user, error = authed_user(request)
        if error:
            return error
        branch, resp_err = _branch_required(_branch_or_none(pk))
        if resp_err:
            return resp_err
        perr = _require_role(user, branch, ROLE_ADMIN)
        if perr:
            return perr
        body = request.data or {}
        target = User.objects.filter(id=body.get("user_id")).first()
        if target is None:
            return json_resp(err(42201, "授权用户不存在"), status=422)
        role = body.get("role")
        if role not in ROLE_VALID:
            return json_resp(err(42201, "角色必须为 VIEWER/OPERATOR/ADMIN"), status=422)
        perm, _ = BranchPermission.objects.update_or_create(
            branch=branch, user=target, defaults={"role": role}
        )
        return json_resp(ok(_serialize_perm(perm)))

    @action(detail=True, methods=["get"])
    def instances(self, request, pk=None):
        """实例轮询：返回此分支全部关联工程的最新实例（读取时推进状态）。"""
        user, error = authed_user(request)
        if error:
            return error
        branch, resp_err = _branch_required(_branch_or_none(pk))
        if resp_err:
            return resp_err
        rows = []
        for bp in branch.branch_projects.select_related("project").all():
            inst = latest_instance(bp)
            if inst:
                advance(inst)
            rows.append(
                {
                    "branch_project_id": bp.id,
                    "project_id": bp.project_id,
                    "project_name": bp.project.name,
                    "instance": serialize_instance(inst) if inst else None,
                }
            )
        return json_resp(ok(rows))


class BranchProjectViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """工程关联：删除 + 启动参数更新 + 启停模拟。"""

    queryset = BranchProject.objects.all()
    permission_classes = [AllowAny]
    http_method_names = ["delete", "put", "post", "head", "options"]

    def destroy(self, request, *args, **kwargs):
        user, error = authed_user(request)
        if error:
            return error
        bp, resp_err = _bp_required(_bp_or_none(kwargs.get("pk")))
        if resp_err:
            return resp_err
        perr = _require_role(user, bp.branch, ROLE_ADMIN)
        if perr:
            return perr
        bp.delete()  # 级联删除启动配置与实例
        return json_resp(ok(message="工程关联已移除"))

    @action(detail=True, methods=["put"])
    def config(self, request, pk=None):
        """更新启动参数（partial）：ADMIN。"""
        user, error = authed_user(request)
        if error:
            return error
        bp, resp_err = _bp_required(_bp_or_none(pk))
        if resp_err:
            return resp_err
        perr = _require_role(user, bp.branch, ROLE_ADMIN)
        if perr:
            return perr
        conf = getattr(bp, "startup_config", None)
        if conf is None:
            conf = StartupConfig.objects.create(branch_project=bp)
        serializer = StartupConfigSerializer(conf, data=request.data, partial=True)
        if not serializer.is_valid():
            return json_resp(err(42201, _first_error(serializer.errors)), status=422)
        conf = serializer.save()
        return json_resp(ok(serialize_config(conf)))

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """启动模拟（OPERATOR 及以上）：重复启动 40903。"""
        user, error = authed_user(request)
        if error:
            return error
        bp, resp_err = _bp_required(_bp_or_none(pk))
        if resp_err:
            return resp_err
        perr = _require_role(user, bp.branch, ROLE_OPERATOR, ROLE_ADMIN)
        if perr:
            return perr
        inst = svc_start(bp, user.username)
        if inst is None:
            return json_resp(err(40903, "实例已在运行"), status=409)
        return json_resp(ok(serialize_instance(inst)))

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        """停止模拟（OPERATOR 及以上）：幂等。"""
        user, error = authed_user(request)
        if error:
            return error
        bp, resp_err = _bp_required(_bp_or_none(pk))
        if resp_err:
            return resp_err
        perr = _require_role(user, bp.branch, ROLE_OPERATOR, ROLE_ADMIN)
        if perr:
            return perr
        inst = svc_stop(bp, user.username)
        return json_resp(ok(serialize_instance(inst) if inst else None))


class BranchPermissionViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """分支授权管理：删除（ADMIN）。"""

    queryset = BranchPermission.objects.select_related("branch", "user").all()
    permission_classes = [AllowAny]
    http_method_names = ["delete", "head", "options"]

    def destroy(self, request, *args, **kwargs):
        user, error = authed_user(request)
        if error:
            return error
        perm = self.get_queryset().filter(pk=kwargs.get("pk")).first()
        if perm is None:
            return json_resp(err(40401, "授权记录不存在"), status=404)
        perr = _require_role(user, perm.branch, ROLE_ADMIN)
        if perr:
            return perr
        perm.delete()
        return json_resp(ok(message="授权已移除"))


# ---------- 轻量辅助视图 ----------

def users_all(request):
    """可用授权用户列表（启用用户）：登录可访问。"""
    user, resp = authed_user(request)
    if resp:
        return resp
    qs = User.objects.filter(is_active=True).order_by("id")
    return json_resp(
        ok(
            [
                {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role}
                for u in qs
            ]
        )
    )


def projects_view(request):
    """工程库列表/创建：登录可访问；重名 40902。"""
    user, resp = authed_user(request)
    if resp:
        return resp
    if request.method == "GET":
        qs = Project.objects.all().order_by("id")
        return json_resp(ok([serialize_project(p) for p in qs]))
    if request.method == "POST":
        body = parse_body(request)
        name = (body.get("name") or "").strip()
        if not name:
            return json_resp(err(42201, "工程名必填"), status=422)
        if Project.objects.filter(name=name).exists():
            return json_resp(err(40902, "工程名已存在"), status=409)
        try:
            project = Project.objects.create(
                name=name,
                repository_url=(body.get("repository_url") or "").strip(),
                description=(body.get("description") or "").strip(),
            )
        except IntegrityError:
            return json_resp(err(40902, "工程名已存在"), status=409)
        return json_resp(ok(serialize_project(project)))
    return json_resp(err(42201, "不支持的请求方法"), status=422)