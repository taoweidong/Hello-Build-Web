"""报告列表过滤器：基于 django-filter 实现（对应报告列表查询）。"""
import django_filters
from django.db.models import Q

from ..models import VerificationReport


class ReportFilter(django_filters.FilterSet):
    """报告列表过滤：status / version_name / strategy_name / keyword。"""

    version_name = django_filters.CharFilter(label="版本", lookup_expr="icontains")
    strategy_name = django_filters.CharFilter(label="策略", lookup_expr="icontains")
    keyword = django_filters.CharFilter(label="关键词", method="filter_keyword")

    class Meta:
        model = VerificationReport
        fields = ["status", "title", "conclusion", "version_name", "strategy_name", "keyword"]

    def filter_keyword(self, queryset, _name: str, value: str):
        """关键词搜索：标题/版本/策略模糊匹配，纯数字同时匹配报告 ID。"""
        cond = Q(title__icontains=value)
        cond |= Q(version_name__icontains=value)
        cond |= Q(strategy_name__icontains=value)
        if value.isdigit():
            cond |= Q(pk=int(value))
        return queryset.filter(cond)