// StrategyEditDialog 模板列表降级重试回归（R4-F13/F-L9）
// 缺陷：首次 getTemplates 失败降级为「当前策略自身模板」单选项后数组非空，
// 后续每次打开都被锁死在降级项且无提示。修复：templatesLoaded 标志区分
// 「成功加载」与「降级」，降级后下次打开自动重试拉取。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import type { VueWrapper } from "@vue/test-utils";
import { ElOption } from "element-plus";

vi.mock("@/api/admin", () => ({
  adminApi: { getTemplates: vi.fn() }
}));
vi.mock("@/api/strategy", () => ({
  previewStrategy: vi.fn(async () => ({ timeline: null, conflict: null })),
  updateStrategy: vi.fn()
}));

import { adminApi } from "@/api/admin";
import StrategyEditDialog from "../shared/StrategyEditDialog.vue";
import type { StrategyItem, TemplateItem } from "@/api/types";

const getTemplatesMock = vi.mocked(adminApi.getTemplates);

function makeStrategy(): StrategyItem {
  return {
    id: 1,
    branch_id: 10,
    branch_name: "main",
    version_id: 1,
    template_id: 7,
    template_name: "标准模板",
    name: "主链路策略",
    build_start_time: "08:00",
    push_mode: "normal",
    push_start_time: null,
    enabled: true
  };
}

function makeTemplate(id: number, name: string): TemplateItem {
  return { id, name, smoke_minutes: 60, analysis_minutes: 30 };
}

let wrapper: VueWrapper;

function mountDialog() {
  wrapper = mount(StrategyEditDialog, {
    props: {
      modelValue: false,
      strategy: makeStrategy(),
      branches: [{ branch_id: 10, branch_name: "main" }]
    },
    global: { stubs: { IconifyIconOffline: true } }
  });
  return wrapper;
}

/** 模板下拉的选项 label 集合（模板选项 label 即模板名，分支选项固定为 main） */
function templateOptionLabels(): string[] {
  return wrapper
    .findAllComponents(ElOption)
    .map(o => o.props("label") as string)
    .filter(l => l !== "main");
}

beforeEach(() => {
  vi.clearAllMocks();
  // 只假造定时器：预览防抖（400ms setTimeout）不在用例内触发；
  // flushPromises 依赖真实 setImmediate，不受影响
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
});

afterEach(() => {
  wrapper?.unmount();
  vi.useRealTimers();
});

describe("R4-F13 StrategyEditDialog 模板列表降级重试", () => {
  it("首次拉取失败降级为策略自身模板；下次打开自动重试并恢复全量选项", async () => {
    getTemplatesMock.mockRejectedValueOnce(new Error("network"));
    mountDialog();

    // 第一次打开：降级为单选项（当前策略自身的模板）
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(getTemplatesMock).toHaveBeenCalledTimes(1);
    expect(templateOptionLabels()).toEqual(["标准模板"]);

    // 关闭后第二次打开：降级不算「已加载」，重试拉取并恢复全量列表
    getTemplatesMock.mockResolvedValue([
      makeTemplate(7, "标准模板"),
      makeTemplate(8, "夜间全量")
    ]);
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(getTemplatesMock).toHaveBeenCalledTimes(2);
    expect(templateOptionLabels()).toEqual(["标准模板", "夜间全量"]);
  });

  it("成功加载后缓存生效：再次打开不重复拉取", async () => {
    getTemplatesMock.mockResolvedValue([makeTemplate(7, "标准模板")]);
    mountDialog();
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(getTemplatesMock).toHaveBeenCalledTimes(1);

    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    // 成功加载置位 templatesLoaded：第三次打开不再发请求
    expect(getTemplatesMock).toHaveBeenCalledTimes(1);
    expect(templateOptionLabels()).toEqual(["标准模板"]);
  });
});
