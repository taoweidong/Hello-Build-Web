// useReportForm 表单状态机单测
import { beforeEach, describe, expect, it, vi } from "vitest";

const warnings: string[] = [];
vi.mock("element-plus", () => ({
  ElMessage: { warning: (m: string) => warnings.push(m), error: vi.fn() }
}));

import { useReportForm } from "@/composables/useReportForm";

describe("useReportForm", () => {
  beforeEach(() => {
    warnings.length = 0;
  });

  it("initNewForm 重置全部字段（不再预填演示假数据）", () => {
    const { form, initNewForm } = useReportForm();
    form.title = "旧标题";
    form.summary = "旧内容";
    initNewForm();
    expect(form.version_name).toBeNull();
    expect(form.strategy_name).toBeNull();
    expect(form.conclusion).toBe("pass");
    expect(form.title).toBe("");
    expect(form.summary).toBe("");
    expect(form.environment).toBe("");
  });

  it("fillForm 从报告回填", () => {
    const { form, fillForm } = useReportForm();
    fillForm({
      id: 1,
      title: "报告A",
      version_name: "27A",
      strategy_name: "27A-master-晚间",
      conclusion: "risk",
      environment: "env",
      summary: "内容",
      risks: "风险",
      remark: "备注",
      status: "draft",
      status_label: "草稿",
      conclusion_label: "有风险",
      created_by_username: "tester1",
      published_at: null,
      publish_count: 0,
      is_updated: false,
      update_count: 0,
      created_at: "2026-10-11T10:00:00",
      updated_at: "2026-10-11T10:00:00"
    });
    expect(form.title).toBe("报告A");
    expect(form.conclusion).toBe("risk");
    expect(form.version_name).toBe("27A");
  });

  it("validateForm：标题/结论/内容必填，版本与策略须成对", () => {
    const { form, validateForm } = useReportForm();
    form.title = "";
    form.summary = "";
    expect(validateForm()).toBe(false);
    expect(warnings).toContain("请填写报告标题");

    form.title = "t";
    expect(validateForm()).toBe(false);
    expect(warnings).toContain("请填写验证内容");

    form.summary = "内容";
    form.version_name = "27A"; // 只选版本不选策略
    expect(validateForm()).toBe(false);
    expect(warnings).toContain("版本与策略须同时选择或均不选择");

    form.strategy_name = "27A-master-晚间";
    expect(validateForm()).toBe(true);
  });

  it("toPayload 序列化：去空格、空值转 undefined", () => {
    const { form, toPayload } = useReportForm();
    form.title = "  标题  ";
    form.summary = " 内容 ";
    form.risks = "  ";
    form.version_name = null;
    form.strategy_name = null;
    const payload = toPayload();
    expect(payload.title).toBe("标题");
    expect(payload.summary).toBe("内容");
    expect(payload.risks).toBe("");
    expect(payload.version_name).toBeUndefined();
    expect(payload.strategy_name).toBeUndefined();
  });
});
