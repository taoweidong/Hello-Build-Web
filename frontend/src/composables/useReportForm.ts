// 验证报告表单状态机：表单数据 / 校验 / 载入与序列化（detail 页专用，纯逻辑可单测）
import { reactive } from "vue";
import { ElMessage } from "element-plus";
import type { ReportForm } from "@/api/report";
import type { ReportItem } from "@/api/types";

export function useReportForm() {
  const form = reactive<ReportForm>({
    title: "",
    version_name: null,
    strategy_name: null,
    conclusion: "pass",
    environment: "",
    summary: "",
    risks: "",
    remark: ""
  });

  /** 新建态初始化：重置全部字段；开发环境预填演示内容便于快速成稿与截图联调 */
  function initNewForm() {
    form.title = "";
    form.version_name = null;
    form.strategy_name = null;
    form.conclusion = "pass";
    form.environment = "";
    form.summary = "";
    form.risks = "";
    form.remark = "";
    if (import.meta.env.DEV) {
      form.title = "27A 冒烟验证报告";
      form.environment = "测试环境（27A 预发）";
      form.summary =
        "针对 27A 版本冒烟策略执行完整验证：核心流程用例 12 项全部通过，未出现阻断性问题。";
      form.risks = "存在 1 项中风险：附件上传偶发延迟（已提单跟踪）。";
      form.remark = "建议次日回归确认风险项后放行发布。";
    }
  }

  function fillForm(r: ReportItem) {
    form.title = r.title;
    form.version_name = r.version_name ?? null;
    form.strategy_name = r.strategy_name ?? null;
    form.conclusion = r.conclusion;
    form.environment = r.environment;
    form.summary = r.summary;
    form.risks = r.risks;
    form.remark = r.remark;
  }

  function validateForm(): boolean {
    if (!form.title.trim()) {
      ElMessage.warning("请填写报告标题");
      return false;
    }
    if (!form.conclusion) {
      ElMessage.warning("请选择验证结论");
      return false;
    }
    if (!form.summary.trim()) {
      ElMessage.warning("请填写验证内容");
      return false;
    }
    if (!!form.version_name !== !!form.strategy_name) {
      ElMessage.warning("版本与策略须同时选择或均不选择");
      return false;
    }
    return true;
  }

  function toPayload(): ReportForm {
    return {
      title: form.title.trim(),
      version_name: form.version_name || undefined,
      strategy_name: form.strategy_name || undefined,
      conclusion: form.conclusion,
      environment: form.environment.trim(),
      summary: form.summary.trim(),
      risks: form.risks.trim(),
      remark: form.remark.trim()
    };
  }

  return { form, initNewForm, fillForm, validateForm, toPayload };
}
