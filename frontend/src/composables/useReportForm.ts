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

  /** 新建态初始化：重置全部字段。

  不预填任何演示内容——旧实现在 DEV 下预填假报告，「新建→直接发布」会把
  假数据一键落库（2026-10-12 质量评估 F-P2-17）。 */
  function initNewForm() {
    form.title = "";
    form.version_name = null;
    form.strategy_name = null;
    form.conclusion = "pass";
    form.environment = "";
    form.summary = "";
    form.risks = "";
    form.remark = "";
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
