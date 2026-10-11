// composables 与共享常量单测
import { describe, expect, it, vi } from "vitest";
import { reportConclusionMeta } from "@/views/constants";

describe("views/constants 展示映射", () => {
  it("报告结论含 risk（有风险）", () => {
    expect(reportConclusionMeta("risk")).toEqual({
      text: "有风险",
      type: "warning"
    });
  });

  it("报告结论未命中时兜底 info", () => {
    expect(reportConclusionMeta("weird")).toEqual({
      text: "weird",
      type: "info"
    });
  });
});

describe("useStrategyPreview 守卫逻辑", () => {
  it("分支/模板未选齐时不调度预览", async () => {
    const previewStrategy = vi.fn().mockResolvedValue({ timeline: {} });
    vi.doMock("@/api/strategy", () => ({
      previewStrategy
    }));
    const { useStrategyPreview } =
      await import("@/composables/useStrategyPreview");
    const form: any = {
      branch_id: 0,
      template_id: 0,
      build_start_time: "22:00"
    };
    const { schedule, run } = useStrategyPreview(() => form, 5);
    schedule();
    await new Promise(r => setTimeout(r, 30));
    expect(previewStrategy).not.toHaveBeenCalled();
    // 选齐后调度生效
    form.branch_id = 1;
    form.template_id = 2;
    schedule();
    await new Promise(r => setTimeout(r, 40));
    expect(previewStrategy).toHaveBeenCalledTimes(1);
    expect(previewStrategy).toHaveBeenCalledWith(
      expect.objectContaining({
        branch_id: 1,
        template_id: 2,
        push_start_time: null
      })
    );
    run();
    await Promise.resolve();
    expect(previewStrategy).toHaveBeenCalledTimes(2);
  });

  it("编辑态透传 id，预览请求排除被编辑策略自身", async () => {
    const previewStrategy = vi.fn().mockResolvedValue({ timeline: {} });
    vi.doMock("@/api/strategy", () => ({
      previewStrategy
    }));
    vi.resetModules(); // 清除上一用例的模块缓存，确保本次 doMock 生效
    const { useStrategyPreview } =
      await import("@/composables/useStrategyPreview");
    const form: any = {
      id: 7,
      branch_id: 1,
      template_id: 2,
      build_start_time: "22:00"
    };
    const { schedule } = useStrategyPreview(() => form, 5);
    schedule();
    await new Promise(r => setTimeout(r, 40));
    expect(previewStrategy).toHaveBeenCalledWith(
      expect.objectContaining({ id: 7, branch_id: 1 })
    );
  });
});
