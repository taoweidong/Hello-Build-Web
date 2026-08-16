"""验证报告业务服务：创建 / 修改 / 发布状态机与修订留痕。

状态机规则：
- draft / published 两态，已发布报告仍可修改，但最终结论 conclusion 锁定不可变更；
- 重复发布视为“更新发布”：publish_count 递增、published_at 刷新；
- 所有写操作（创建 / 修改 / 发布）均写入 ReportRevisionLog，
  按时间倒序（由近及远）查阅即可还原报告每次修改。
"""
from typing import Dict, List, Tuple

from django.utils import timezone

from ..models import ReportRevisionLog, VerificationReport

# 可编辑字段（字段名, 中文标签），字段级 diff 留痕时使用中文标签展示
EDITABLE_FIELDS: List[Tuple[str, str]] = [
    ("title", "标题"),
    ("version_name", "版本"),
    ("strategy_name", "策略"),
    ("conclusion", "结论"),
    ("environment", "验证环境"),
    ("summary", "验证内容"),
    ("risks", "问题与风险"),
    ("remark", "备注"),
]


class ReportConclusionLockedError(Exception):
    """最终结论锁定异常：已发布报告的结论不可修改。"""


class ReportService:
    """验证报告业务服务：create / update / publish / revisions / log。"""

    @classmethod
    def create(cls, username: str, data: Dict) -> VerificationReport:
        """创建草稿报告并写入创建留痕。"""
        report = VerificationReport.objects.create(
            title=data["title"].strip(),
            version_name=(data.get("version_name") or "").strip(),
            strategy_name=(data.get("strategy_name") or "").strip(),
            conclusion=data["conclusion"],
            environment=(data.get("environment") or "").strip(),
            summary=data["summary"].strip(),
            risks=(data.get("risks") or "").strip(),
            remark=(data.get("remark") or "").strip(),
            status="draft",
            created_by_username=username,
        )
        cls.log(report, "create", "创建报告", "", report.title, username)
        return report

    @classmethod
    def update(cls, username: str, report: VerificationReport, data: Dict) -> VerificationReport:
        """更新报告：已发布报告可改非结论字段，结论变更抛错，字段级 diff 留痕。"""
        if report.status == "published":
            new_conclusion = data.get("conclusion")
            if new_conclusion and new_conclusion != report.conclusion:
                raise ReportConclusionLockedError("报告已发布，最终结论不可修改")
        changes: List[Tuple[str, str, str]] = []
        for field, label in EDITABLE_FIELDS:
            if field == "conclusion" and report.status == "published":
                # 结论锁定：已发布态不参与 diff（值不同时上方已拦截）
                continue
            new_value = data.get(field)
            if new_value is None:
                continue
            new_value = str(new_value).strip()
            old_value = getattr(report, field)
            if isinstance(old_value, str):
                old_value = old_value.strip()
            if new_value != old_value:
                changes.append((label, old_value, new_value))
                setattr(report, field, new_value)
        if changes:
            report.save()
            for label, before, after in changes:
                cls.log(report, "update", label, before, after, username)
        return report

    @classmethod
    def publish(cls, username: str, report: VerificationReport) -> VerificationReport:
        """发布报告：刷新发布时间、发布次数 +1，重复发布标记为更新发布。"""
        is_update = report.publish_count > 0
        before_count = report.publish_count
        report.status = "published"
        report.published_at = timezone.now()
        report.publish_count += 1
        report.save(update_fields=["status", "published_at", "publish_count", "updated_at"])
        cls.log(
            report,
            "publish",
            "更新发布" if is_update else "发布报告",
            f"发布次数 {before_count}",
            f"发布次数 {report.publish_count}",
            username,
        )
        return report

    @classmethod
    def revisions(cls, report_id: int) -> List[ReportRevisionLog]:
        """报告修改记录：按时间倒序（由近及远）。"""
        return list(ReportRevisionLog.objects.filter(report_id=report_id).order_by("-id"))

    @classmethod
    def log(
        cls,
        report: VerificationReport,
        action: str,
        field_name: str,
        before_value: str,
        after_value: str,
        operator_username: str,
    ) -> ReportRevisionLog:
        """修订留痕统一入口：写入一条 ReportRevisionLog。"""
        return ReportRevisionLog.objects.create(
            report_id=report.id,
            report_title=report.title,
            action=action,
            field_name=field_name,
            before_value=before_value,
            after_value=after_value,
            operator_username=operator_username,
        )