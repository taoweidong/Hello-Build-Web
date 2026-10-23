// BookingDialog 组件级测试（R6-F5/F10/F16：此前零覆盖）
// 锁定：校验不过不发请求（stub ElForm 锁守卫分支——EP 校验在 jsdom 下对空必填
// 也放行，不能依赖其真实行为）、超窗口拦截、成功抢占后 emit booked 且关闭弹窗
//（R6-F5：此前成功不关闭，与其余弹窗口径不一致）、挂载即开也拉取版本计划
//（R6-F16：ScheduleDialogs 以 v-if 挂载，watch 需 immediate）
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import type { VueWrapper } from "@vue/test-utils";
import { ElMessage } from "element-plus";
import { defineComponent } from "vue";

vi.mock("@/api/plan", () => ({ getPlan: vi.fn() }));
vi.mock("@/api/slotBooking", () => ({ createBooking: vi.fn() }));

import { createBooking } from "@/api/slotBooking";
import { getPlan } from "@/api/plan";
import BookingDialog from "../shared/BookingDialog.vue";
import { makeTemplate } from "./fixtures";

const createMock = vi.mocked(createBooking);
const planMock = vi.mocked(getPlan);

let wrapper: VueWrapper;

/** validate 恒 reject 的 ElForm 替身：锁定组件「校验不过 → 不发请求」守卫分支 */
const RejectingForm = defineComponent({
  name: "ElForm",
  setup(_, { slots, expose }) {
    expose({
      validate: vi.fn().mockRejectedValue(new Error("invalid")),
      clearValidate: () => {},
      resetFields: () => {}
    });
    return () => slots.default?.();
  }
});

function mountDialog(
  over: Partial<Record<string, unknown>> = {},
  stubs: Record<string, unknown> = {}
) {
  wrapper = mount(BookingDialog, {
    props: {
      modelValue: true,
      date: "2026-10-14",
      template: makeTemplate(),
      horizonEnd: "2026-12-11",
      ...over
    },
    global: { stubs: { IconifyIconOffline: true, ...stubs } }
  });
  return wrapper;
}

/** 经 setupState 预填表单（script setup 组件的标准测试通道） */
function fillForm(form: {
  version_id: number | null;
  branch_id: number | null;
  purpose: string;
}) {
  const setupState = (
    wrapper.vm.$ as unknown as {
      setupState: { form: Record<string, unknown> };
    }
  ).setupState;
  Object.assign(setupState.form, form);
}

/** 底部「确认抢占」按钮 */
function submitButton(): HTMLButtonElement {
  return wrapper.findAll("button").find(b => b.text().includes("确认抢占"))!
    .element as HTMLButtonElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  planMock.mockResolvedValue([
    {
      version_id: 3,
      version_name: "v3.2",
      branches: [{ branch_id: 20, branch_name: "release" }]
    }
  ] as never);
  createMock.mockResolvedValue({} as never);
});

afterEach(() => {
  wrapper?.unmount();
  document.body.innerHTML = "";
});

describe("BookingDialog 抢占弹窗", () => {
  it("成功抢占：emit booked 并 emit update:modelValue(false)（R6-F5 成功即关）", async () => {
    mountDialog();
    await flushPromises();
    fillForm({ version_id: 3, branch_id: 20, purpose: "回归验证" });
    submitButton().dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    expect(createMock).toHaveBeenCalledTimes(1);
    expect(wrapper.emitted("booked")).toHaveLength(1);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("校验不过不发请求（stub ElForm validate 恒 reject，锁守卫分支）", async () => {
    mountDialog({}, { ElForm: RejectingForm });
    await flushPromises();
    fillForm({ version_id: 3, branch_id: 20, purpose: "" });
    submitButton().dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    expect(createMock).not.toHaveBeenCalled();
  });

  it("超出可抢占窗口拦截：不发请求并告警", async () => {
    const warningSpy = vi.spyOn(ElMessage, "warning");
    mountDialog({ date: "2027-06-01" });
    await flushPromises();
    fillForm({ version_id: 3, branch_id: 20, purpose: "回归验证" });
    submitButton().dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    expect(createMock).not.toHaveBeenCalled();
    expect(warningSpy).toHaveBeenCalledWith("超出可抢占窗口，请选择更近的日期");
    warningSpy.mockRestore();
  });

  it("打开时拉取版本计划供关联选择（getPlan 以日期为锚）", async () => {
    mountDialog();
    await flushPromises();
    expect(planMock).toHaveBeenCalledWith({ date: "2026-10-14" });
    // 打开失败降级空集不阻塞渲染（弹窗仍可用，关联版本选择为空由校验兜底）
    planMock.mockRejectedValueOnce(new Error("network"));
  });
});
