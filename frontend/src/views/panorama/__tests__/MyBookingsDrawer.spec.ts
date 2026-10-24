// MyBookingsDrawer 组件级测试（R7-F1：此前零覆盖——R6 既有覆盖缺口第 3 条）
// 挂载即开初始化缺陷正是本 spec 实证暴露的：ScheduleDialogs 以 v-if 挂载
// 本抽屉（挂载即 modelValue=true），而 element-plus useDialog 的 @open 只在
// 非 immediate 的 modelValue watcher 里发出，挂载即开时永不触发。
// 锁定：挂载即开拉取列表（R7-F1）、释放确认流转、changed 事件回触
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import type { VueWrapper } from "@vue/test-utils";
import { ElMessageBox } from "element-plus";

// spyOn 替换确认框（整模块 vi.mock 会破坏 SFC 模板对 EP 组件的解析，勿用）
vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(undefined as never);

vi.mock("@/api/slotBooking", () => ({
  getMyBookings: vi.fn(),
  releaseBooking: vi.fn()
}));

import { getMyBookings, releaseBooking } from "@/api/slotBooking";
import MyBookingsDrawer from "../shared/MyBookingsDrawer.vue";
import { bookingStatusMeta } from "@/views/constants";

const getMyBookingsMock = vi.mocked(getMyBookings);
const releaseMock = vi.mocked(releaseBooking);

let wrapper: VueWrapper;

const ROW = {
  id: 100,
  date: "2026-10-26",
  template_name: "早间窗口",
  start_time: "09:00",
  end_time: "10:00",
  purpose: "联调占用",
  status: "reserved",
  version_name: "27A",
  branch_name: "master",
  created_at: "2026-10-25T08:00:00",
  release_reason: null
};

function mountDrawer(modelValue = true) {
  wrapper = mount(MyBookingsDrawer, {
    props: { modelValue }
  });
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  // vitest restoreMocks: true 会在每个用例前还原 spyOn：确认框桩必须在 beforeEach 重设
  vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(undefined as never);
  getMyBookingsMock.mockResolvedValue({
    items: [ROW],
    total: 1,
    page: 1,
    page_size: 20
  } as never);
  releaseMock.mockResolvedValue({} as never);
});

afterEach(() => {
  wrapper?.unmount();
  document.body.innerHTML = "";
});

describe("MyBookingsDrawer 我的抢占抽屉", () => {
  it("挂载即开（modelValue=true）自动拉取列表（R7-F1：@open 在挂载即开下不触发）", async () => {
    mountDrawer(true);
    await flushPromises();
    expect(getMyBookingsMock).toHaveBeenCalledWith(1, 20);
    expect(wrapper.text()).toContain("联调占用");
    expect(wrapper.text()).toContain(bookingStatusMeta("reserved").text);
  });

  it("非挂载即开（modelValue=false）不拉取；常规打开（false→true 触发 @open）拉取一次", async () => {
    mountDrawer(false);
    await flushPromises();
    expect(getMyBookingsMock).not.toHaveBeenCalled();
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    // false→true 的变迁走 useDialog 非 immediate watcher → @open → load；
    // 挂载即开（true 挂载）则由 onMounted 兜底（上一用例）
    expect(getMyBookingsMock).toHaveBeenCalledTimes(1);
  });

  it("释放确认流转：成功后重拉列表并 emit changed", async () => {
    mountDrawer(true);
    await flushPromises();
    getMyBookingsMock.mockClear();
    await wrapper
      .findAll("button")
      .find(b => b.text().includes("释放"))!
      .trigger("click");
    await flushPromises();
    expect(releaseMock).toHaveBeenCalledWith(100);
    expect(getMyBookingsMock).toHaveBeenCalledTimes(1);
    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("释放失败：不 emit changed（拦截器已提示），列表保持", async () => {
    releaseMock.mockRejectedValue(new Error("40904") as never);
    mountDrawer(true);
    await flushPromises();
    getMyBookingsMock.mockClear();
    await wrapper
      .findAll("button")
      .find(b => b.text().includes("释放"))!
      .trigger("click");
    await flushPromises();
    expect(wrapper.emitted("changed")).toBeUndefined();
  });
});
