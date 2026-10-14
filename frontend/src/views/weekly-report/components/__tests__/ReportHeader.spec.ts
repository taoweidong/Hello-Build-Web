// ReportHeader 本周进度格点边界回归（R4-F4/F-M1）
// 缺陷：今天=所展示周周日时 elapsed=7，原 today 条件要求 elapsed<7 →
// 当天 7 格全实心、呼吸圈消失（R3-F11 修复引入的边界回归）。
import { describe, expect, it } from "vitest";
import { mount, type VueWrapper } from "@vue/test-utils";
import ReportHeader from "../ReportHeader.vue";

/** weekStart 固定为周一（2026-10-12 是周一）；today 按场景注入 */
function mountHeader(weekStart: string, today: string): VueWrapper {
  return mount(ReportHeader, {
    props: {
      weekStart,
      today,
      weekRangeText: `${weekStart} ~ ${today}`,
      versionName: "27A",
      canEdit: true,
      loading: false,
      lastLoadedAt: null
    },
    global: {
      // 离线图标组件由 main.ts 全局注册，测试环境不存在；空 stub 避免解析告警
      stubs: { IconifyIconOffline: true }
    }
  });
}

function pipStates(wrapper: VueWrapper) {
  return wrapper.findAll(".wp-pip").map(p => ({
    done: p.classes().includes("done"),
    today: p.classes().includes("today")
  }));
}

describe("R4-F4 ReportHeader 本周进度格点", () => {
  it("今天=本周周日：7 格全实心且末格仍带 today 呼吸圈（F-M1 回归锁定）", () => {
    const pips = pipStates(mountHeader("2026-10-12", "2026-10-18"));
    expect(pips).toHaveLength(7);
    expect(pips.every(p => p.done)).toBe(true);
    expect(pips[6].today).toBe(true);
    expect(pips.slice(0, 6).some(p => p.today)).toBe(false);
  });

  it("今天=周一：首格 done+today，其余空心", () => {
    const pips = pipStates(mountHeader("2026-10-12", "2026-10-12"));
    expect(pips[0]).toEqual({ done: true, today: true });
    expect(pips.slice(1).some(p => p.done || p.today)).toBe(false);
  });

  it("周中（周三）：前 3 格实心且第 3 格为 today", () => {
    const pips = pipStates(mountHeader("2026-10-12", "2026-10-14"));
    expect(pips.filter(p => p.done)).toHaveLength(3);
    expect(pips[2].today).toBe(true);
  });

  it("历史周（整周已过去）：全实心且无 today 标记（R3-F11 语义保留）", () => {
    const pips = pipStates(mountHeader("2026-10-05", "2026-10-13"));
    expect(pips.every(p => p.done)).toBe(true);
    expect(pips.some(p => p.today)).toBe(false);
  });

  it("未来周：全空心，无 done 无 today", () => {
    const pips = pipStates(mountHeader("2026-10-19", "2026-10-13"));
    expect(pips.some(p => p.done || p.today)).toBe(false);
  });

  it("进度文案：今天=本周周日显示 7/7", () => {
    const wrapper = mountHeader("2026-10-12", "2026-10-18");
    expect(wrapper.find(".wp-label").text()).toContain("7/7");
  });
});
