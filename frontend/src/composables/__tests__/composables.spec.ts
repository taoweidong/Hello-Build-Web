// composables 与共享常量单测
import { describe, expect, it, vi } from "vitest";
import {
  pushStatusMeta,
  reportConclusionMeta,
  roundConclusionMeta
} from "@/views/constants";
import { buildPlanRows } from "@/composables/useGanttRows";

describe("views/constants 展示映射", () => {
  it("轮次结论：命中与兜底", () => {
    expect(roundConclusionMeta("pass")).toEqual({
      text: "通过",
      type: "success"
    });
    expect(roundConclusionMeta("fail").type).toBe("danger");
    expect(roundConclusionMeta("pending").text).toBe("待录");
    expect(roundConclusionMeta("unknown")).toEqual({
      text: "unknown",
      type: "info"
    });
    expect(roundConclusionMeta("").text).toBe("待录");
  });

  it("报告结论含 risk（有风险）", () => {
    expect(reportConclusionMeta("risk")).toEqual({
      text: "有风险",
      type: "warning"
    });
  });

  it("推送状态：命中与兜底", () => {
    expect(pushStatusMeta("success")).toEqual({
      text: "成功",
      type: "success"
    });
    expect(pushStatusMeta("failed").type).toBe("danger");
    expect(pushStatusMeta("")).toEqual({ text: "-", type: "info" });
  });
});

describe("useGanttRows 行构建逻辑（纯函数部分）", () => {
  const planData = [
    {
      version_id: 1,
      version_name: "27A",
      pm_name: "pm",
      branches: [
        {
          branch_id: 11,
          branch_name: "master",
          strategies: [
            {
              id: 101,
              name: "晚间全量",
              push_mode: "normal",
              build_start_time: "22:00",
              push_start_time: null,
              enabled: true,
              conflict: true,
              timeline: {
                push: null,
                build: {
                  start: "2026-10-11T22:00:00",
                  end: "2026-10-11T22:30:00"
                },
                smoke: {
                  start: "2026-10-11T22:30:00",
                  end: "2026-10-12T06:30:00"
                },
                analysis: {
                  start: "2026-10-12T06:30:00",
                  end: "2026-10-12T08:30:00"
                }
              }
            },
            {
              id: 102,
              name: "同步推送",
              push_mode: "sync",
              build_start_time: "23:00",
              push_start_time: null,
              enabled: true,
              conflict: false,
              timeline: {
                push: {
                  start: "2026-10-11T22:10:00",
                  end: "2026-10-11T22:30:00"
                },
                build: {
                  start: "2026-10-11T23:00:00",
                  end: "2026-10-11T23:30:00"
                },
                smoke: {
                  start: "2026-10-11T23:30:00",
                  end: "2026-10-12T07:30:00"
                },
                analysis: {
                  start: "2026-10-12T07:30:00",
                  end: "2026-10-12T09:30:00"
                }
              }
            }
          ]
        }
      ]
    }
  ];

  it("每个「版本+分支」生成一行，阶段色块齐全", () => {
    const rows = buildPlanRows(planData);
    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe("b-11");
    expect(rows[0].label).toBe("27A / master");
    // 策略101：build/smoke/analysis（无 push）；策略102：push+build/smoke/analysis
    const keys = rows[0].phases.map(p => p.key);
    expect(keys).toEqual([
      "101-build",
      "101-smoke",
      "101-analysis",
      "102-push",
      "102-build",
      "102-smoke",
      "102-analysis"
    ]);
  });

  it("冲突标记透传到非 push 阶段，push 恒不标红", () => {
    const rows = buildPlanRows(planData);
    const s101 = rows[0].phases.filter(p => p.key.startsWith("101"));
    expect(s101.every(p => p.conflict === true)).toBe(true);
    const push = rows[0].phases.find(p => p.key === "102-push");
    expect(push?.conflict).toBe(false);
  });

  it("色块携带版本/策略名供点击回查", () => {
    const rows = buildPlanRows(planData);
    const first = rows[0].phases[0];
    expect(first.versionName).toBe("27A");
    expect(first.strategyName).toBe("晚间全量");
  });

  it("无 timeline 的策略被跳过", () => {
    const data = JSON.parse(JSON.stringify(planData));
    data[0].branches[0].strategies[0].timeline = undefined;
    const rows = buildPlanRows(data);
    expect(rows[0].phases.every(p => p.key.startsWith("102"))).toBe(true);
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
