// SlotDetailDialog 组件级测试（R6-F10：此前零覆盖，布局 spec 中被 stub）
// 锁定：isMine 驱动的释放/改期入口、释放确认流转（:loading 在途、失败保留）、
// 「改期」事件转发、他人抢占提示
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import type { VueWrapper } from "@vue/test-utils";
import { ElMessageBox } from "element-plus";

// spyOn 替换确认框（整模块 vi.mock 会破坏 SFC 模板对 EP 组件的解析，勿用）
vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(undefined as never);

vi.mock("@/api/slotBooking", () => ({ releaseBooking: vi.fn() }));

import { releaseBooking } from "@/api/slotBooking";
import SlotDetailDialog from "../shared/SlotDetailDialog.vue";
import { makeBooking, makeCell, makeTemplate } from "./fixtures";

const releaseMock = vi.mocked(releaseBooking);

let wrapper: VueWrapper;

function mountDialog(
  over: {
    entryBookingMine?: boolean;
    reschedulable?: boolean;
  } = {}
) {
  const booking = makeBooking({ is_mine: over.entryBookingMine ?? true });
  wrapper = mount(SlotDetailDialog, {
    props: {
      modelValue: true,
      date: "2026-10-13",
      entry: makeCell({ status: "reserved", booking }),
      template: makeTemplate(),
      reschedulable: over.reschedulable ?? true
    },
    global: { stubs: { IconifyIconOffline: true } }
  });
  return wrapper;
}

function footerButtons(): HTMLButtonElement[] {
  return wrapper.findAll("button").map(b => b.element as HTMLButtonElement);
}

beforeEach(() => {
  vi.clearAllMocks();
  // vitest restoreMocks: true 会在每个用例前还原 spyOn：确认框桩必须在 beforeEach 重设
  vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(undefined as never);
  releaseMock.mockResolvedValue({} as never);
});

afterEach(() => {
  wrapper?.unmount();
  document.body.innerHTML = "";
});

describe("SlotDetailDialog 抢占详情弹窗", () => {
  it("我的抢占：显示「释放该时段」与「改期」，展示抢占人/用途/关联", async () => {
    mountDialog({ entryBookingMine: true, reschedulable: true });
    await flushPromises(); // el-dialog 内容异步渲染，先 flush 再查 DOM
    const texts = wrapper.findAll("button").map(b => b.text());
    expect(texts).toContain("释放该时段");
    expect(texts).toContain("改期");
    expect(wrapper.text()).toContain("张三");
    expect(wrapper.text()).toContain("集成验证");
  });

  it("他人抢占：不显示释放入口（admin 改期他人按 canReschedule 权限位放行，属设计口径）", async () => {
    mountDialog({ entryBookingMine: false, reschedulable: false });
    await flushPromises();
    const texts = wrapper.findAll("button").map(b => b.text());
    expect(texts).not.toContain("释放该时段");
    expect(texts).not.toContain("改期");
    expect(wrapper.text()).toContain("该时段已被他人抢占");
  });

  it("释放确认流转：请求在途按钮 loading，成功 emit released", async () => {
    let resolveFn!: (v: unknown) => void;
    releaseMock.mockReturnValue(
      new Promise(r => {
        resolveFn = r;
      }) as never
    );
    mountDialog({ entryBookingMine: true });
    await flushPromises();
    const releaseBtn = wrapper
      .findAll("button")
      .find(b => b.text().includes("释放该时段"))!;
    releaseBtn.trigger("click");
    await flushPromises();
    expect(releaseMock).toHaveBeenCalledWith(100);
    // 在途守卫：释放中按钮呈 loading（防双击并发重复释放）
    const loadingBtn = footerButtons().find(b =>
      b.classList.contains("is-loading")
    );
    expect(loadingBtn).toBeTruthy();

    resolveFn(undefined);
    await flushPromises();
    expect(wrapper.emitted("released")).toHaveLength(1);
    // finally 复位
    expect(
      footerButtons().find(b => b.classList.contains("is-loading"))
    ).toBeUndefined();
  });

  it("自释放成功后关闭弹窗（R7-F8：对齐动作总线 release 路径，旧数据不滞留屏上）", async () => {
    mountDialog({ entryBookingMine: true });
    await flushPromises();
    await wrapper
      .findAll("button")
      .find(b => b.text().includes("释放该时段"))!
      .trigger("click");
    await flushPromises();
    expect(wrapper.emitted("released")).toHaveLength(1);
    expect(wrapper.emitted("update:modelValue")).toEqual([[false]]);
  });

  it("空闲时段（无 booking）展示空态而非空壳（R7-F8）", async () => {
    wrapper = mount(SlotDetailDialog, {
      props: {
        modelValue: true,
        date: "2026-10-13",
        entry: makeCell({ status: "available", booking: null }),
        template: makeTemplate()
      },
      global: { stubs: { IconifyIconOffline: true } }
    });
    await flushPromises();
    expect(wrapper.text()).toContain("该时段暂无抢占记录");
    // 空态仍给出时段上下文（模板名与起止时间）
    expect(wrapper.text()).toContain("早间窗口");
    expect(wrapper.text()).toContain("09:00");
    const texts = wrapper.findAll("button").map(b => b.text());
    expect(texts).not.toContain("释放该时段");
  });

  it("释放失败：不 emit released，弹窗状态保留（拦截器已提示）", async () => {
    releaseMock.mockRejectedValue(new Error("40904") as never);
    mountDialog({ entryBookingMine: true });
    await flushPromises();
    await wrapper
      .findAll("button")
      .find(b => b.text().includes("释放该时段"))!
      .trigger("click");
    await flushPromises();
    expect(wrapper.emitted("released")).toBeUndefined();
  });

  it("「改期」按钮只转发事件（预填编排留在动作总线）", async () => {
    mountDialog({ entryBookingMine: true, reschedulable: true });
    await flushPromises();
    await wrapper
      .findAll("button")
      .find(b => b.text() === "改期")!
      .trigger("click");
    expect(wrapper.emitted("reschedule")).toHaveLength(1);
  });
});
