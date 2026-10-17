// 策略页「保存策略」在途守卫组件级回归（R5-F3）
// 缺陷复现口径：confirm 通过后请求在途期间双击「保存策略」，并发两次
// createStrategy/updateStrategy 产生重复策略。修复范式对齐 admin 各 Tab：
// saving ref + 入口守卫 + try/finally 置位 + 按钮 :loading。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick, ref } from "vue";
import type { VueWrapper } from "@vue/test-utils";

// 只替换 ElMessageBox（确认框直接通过），ElMessage 等保持真实
vi.mock("element-plus", async importOriginal => {
  const actual = await importOriginal<typeof import("element-plus")>();
  return {
    ...actual,
    ElMessageBox: {
      confirm: vi.fn().mockResolvedValue(undefined),
      alert: vi.fn().mockResolvedValue(undefined)
    }
  };
});

// 页面用到 useRoute/useRouter（query.id 编辑深链），单测直接桩掉避免拉起 router
vi.mock("vue-router", () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() })
}));

vi.mock("@/api/strategy", () => ({
  getStrategies: vi.fn().mockResolvedValue([]),
  createStrategy: vi.fn(),
  updateStrategy: vi.fn(),
  toggleStrategy: vi.fn()
}));
vi.mock("@/api/admin", () => ({
  adminApi: { getTemplates: vi.fn().mockResolvedValue([]) }
}));
vi.mock("@/api/plan", () => ({ getPlan: vi.fn().mockResolvedValue([]) }));
// 预览 composable 桩：preview 恒 null（无冲突，保存按钮可用）
vi.mock("@/composables/useStrategyPreview", () => ({
  useStrategyPreview: () => ({
    preview: ref(null),
    schedule: vi.fn(),
    reset: vi.fn()
  })
}));
// getCurrentUser 桩为已绑定版本的 PM（其余工具保持真实实现）
vi.mock("@/utils/business", async importOriginal => {
  const actual = await importOriginal<typeof import("@/utils/business")>();
  return {
    ...actual,
    getCurrentUser: () => ({ bound_version_id: 1, bound_version_name: "27A" })
  };
});

import {
  getStrategies,
  createStrategy,
  updateStrategy
} from "@/api/strategy";
import { getPlan } from "@/api/plan";
import { adminApi } from "@/api/admin";
import StrategyIndex from "../index.vue";

const createMock = vi.mocked(createStrategy);
const updateMock = vi.mocked(updateStrategy);

let wrapper: VueWrapper;

beforeEach(() => {
  vi.clearAllMocks();
  // restoreMocks 会还原工厂里预设的 resolved 值：每个用例前显式重建默认桩
  vi.mocked(getStrategies).mockResolvedValue([]);
  vi.mocked(getPlan).mockResolvedValue([]);
  vi.mocked(adminApi.getTemplates).mockResolvedValue([]);
});

afterEach(() => {
  wrapper?.unmount();
  document.body.innerHTML = "";
});

/** 制造一个悬挂的请求（测试在途状态用） */
function pending<T>() {
  let resolveFn!: (v: T) => void;
  const promise = new Promise<T>(r => {
    resolveFn = r;
  });
  return { promise, resolveFn };
}

/** 「保存策略」按钮（form-actions 区第一个主按钮） */
function saveButton(w: VueWrapper): HTMLButtonElement {
  return w
    .findAll(".form-actions button")
    .find(b => b.text().includes("保存策略"))!
    .element as HTMLButtonElement;
}

describe("R5-F3 策略页保存在途守卫", () => {
  it("新建路径：请求在途时按钮呈 loading，双击仅发一次 createStrategy，完成后复位", async () => {
    const { promise, resolveFn } =
      pending<Awaited<ReturnType<typeof createStrategy>>>();
    createMock.mockReturnValue(promise);
    wrapper = mount(StrategyIndex);
    await flushPromises();

    const save = saveButton(wrapper);
    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    // confirm 桩 resolve 后进入在途：saving=true → createStrategy 已发出
    await flushPromises();
    expect(createMock).toHaveBeenCalledTimes(1);
    expect(save.classList.contains("is-loading")).toBe(true);

    // 双击第二次：EP loading 禁用 + onSave 入口守卫双保险，不得并发第二次
    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await nextTick();
    await flushPromises();
    expect(createMock).toHaveBeenCalledTimes(1);

    resolveFn({} as Awaited<ReturnType<typeof createStrategy>>);
    await flushPromises();
    expect(save.classList.contains("is-loading")).toBe(false);
  });

  it("create 失败：loading 复位且不再重复提交", async () => {
    createMock.mockRejectedValue(new Error("40901"));
    wrapper = mount(StrategyIndex);
    await flushPromises();

    const save = saveButton(wrapper);
    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    expect(createMock).toHaveBeenCalledTimes(1);
    // finally 复位：失败后按钮恢复可点（保留表单供修改重试）
    expect(save.classList.contains("is-loading")).toBe(false);
  });

  it("编辑路径：在途时双击仅发一次 updateStrategy", async () => {
    const { promise, resolveFn } =
      pending<Awaited<ReturnType<typeof updateStrategy>>>();
    updateMock.mockReturnValue(promise);
    // 通过行内「编辑」进入编辑态（isEditing → 走 updateStrategy）
    vi.mocked(getStrategies).mockResolvedValue([
      {
        id: 9,
        name: "27A-TR5-晚间全量",
        branch_id: 3,
        branch_name: "TR5",
        template_id: 1,
        template_name: "晚间全量冒烟",
        build_start_time: "22:00",
        push_start_time: null,
        push_mode: "normal",
        enabled: true
      } as never
    ]);
    wrapper = mount(StrategyIndex);
    await flushPromises();
    await wrapper
      .findAll("button")
      .find(b => b.text().includes("编辑"))!
      .trigger("click");

    const save = saveButton(wrapper);
    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    expect(updateMock).toHaveBeenCalledTimes(1);
    expect(save.classList.contains("is-loading")).toBe(true);

    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await nextTick();
    await flushPromises();
    expect(updateMock).toHaveBeenCalledTimes(1);

    resolveFn({} as Awaited<ReturnType<typeof updateStrategy>>);
    await flushPromises();
    expect(save.classList.contains("is-loading")).toBe(false);
  });
});
