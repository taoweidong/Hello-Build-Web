// UsersTab / TemplatesTab 保存按钮 :loading 在途守卫组件级回归（R4-F3/F-H3）
// 缺陷复现口径：双击「保存」并发两次 create，第二次撞 40902 重名弹错。
// 修复范式对齐 VersionsTab：saving ref + try/finally 置位 + 按钮 :loading + 在途守卫。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { nextTick } from "vue";
import type { VueWrapper } from "@vue/test-utils";

vi.mock("@/api/admin", () => ({
  adminApi: {
    createUser: vi.fn(),
    updateUser: vi.fn(),
    createTemplate: vi.fn(),
    updateTemplate: vi.fn(),
    deleteTemplate: vi.fn()
  }
}));

import { ElMessage } from "element-plus";
import { adminApi } from "@/api/admin";
import UsersTab from "../UsersTab.vue";
import TemplatesTab from "../TemplatesTab.vue";

const createUserMock = vi.mocked(adminApi.createUser);
const createTemplateMock = vi.mocked(adminApi.createTemplate);
const updateTemplateMock = vi.mocked(adminApi.updateTemplate);

let wrapper: VueWrapper;

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  wrapper?.unmount();
  // 弹窗 teleport 到 body：清理残留节点，避免跨用例串扰
  document.body.innerHTML = "";
});

/** 原生 input 事件写值（el-input 的 v-model 监听 input 事件） */
function setInput(input: HTMLInputElement, value: string) {
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

/** 弹窗底部「保存」按钮（footer 顺序固定：取消、保存）。
 * el-dialog 默认不 append-to-body：弹窗 DOM 在 wrapper 元素内（未 attach 到
 * document），故一律经 wrapper 查询而非 document。 */
function saveButton(w: VueWrapper): HTMLButtonElement {
  const btns = w.findAll(".el-dialog__footer button");
  return btns[btns.length - 1].element as HTMLButtonElement;
}

/** 弹窗表单项列表 */
function formItems(w: VueWrapper) {
  return w.findAll(".el-dialog .el-form-item");
}

/** 制造一个悬挂的 create 请求（测试在途状态用） */
function pendingCreate<T>() {
  let resolveFn!: (v: T) => void;
  const promise = new Promise<T>(r => {
    resolveFn = r;
  });
  return { promise, resolveFn };
}

describe("R4-F3 UsersTab 保存在途守卫", () => {
  it("请求在途时保存按钮呈 loading，双击仅发一次 create，完成后复位并通知刷新", async () => {
    const { promise, resolveFn } =
      pendingCreate<Awaited<ReturnType<typeof adminApi.createUser>>>();
    createUserMock.mockReturnValue(promise);
    wrapper = mount(UsersTab, { props: { users: [] } });

    await wrapper
      .findAll("button")
      .find(b => b.text().includes("新建用户"))!
      .trigger("click");
    await flushPromises();

    // 表单前两项：用户名 / 初始密码（新建路径两者必填）
    const items = formItems(wrapper);
    setInput(items[0].find("input").element as HTMLInputElement, "u_new");
    setInput(items[1].find("input").element as HTMLInputElement, "pwd123456");
    await nextTick();

    const save = saveButton(wrapper);
    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await nextTick();
    expect(createUserMock).toHaveBeenCalledTimes(1);
    // 在途状态外化到按钮（:loading → is-loading）
    expect(save.classList.contains("is-loading")).toBe(true);

    // 双击第二次：EP loading 禁用 + saveUser 在途守卫双保险，不得并发第二次
    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await nextTick();
    expect(createUserMock).toHaveBeenCalledTimes(1);

    resolveFn({} as Awaited<ReturnType<typeof adminApi.createUser>>);
    await flushPromises();
    expect(save.classList.contains("is-loading")).toBe(false);
    expect(wrapper.emitted("refresh")).toBeTruthy();
  });

  it("create 失败：loading 复位且弹窗保留（供修改重试）", async () => {
    createUserMock.mockRejectedValue(new Error("40902"));
    wrapper = mount(UsersTab, { props: { users: [] } });
    await wrapper
      .findAll("button")
      .find(b => b.text().includes("新建用户"))!
      .trigger("click");
    await flushPromises();
    const items = formItems(wrapper);
    setInput(items[0].find("input").element as HTMLInputElement, "u_dup");
    setInput(items[1].find("input").element as HTMLInputElement, "pwd123456");
    await nextTick();

    const save = saveButton(wrapper);
    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    expect(save.classList.contains("is-loading")).toBe(false);
    // 失败不 emit refresh（弹窗保留由 userDialog 状态承载，未被关闭）
    expect(wrapper.emitted("refresh")).toBeFalsy();
    expect(wrapper.find(".el-dialog").exists()).toBe(true);
  });
});

describe("R5-B12 TemplatesTab 时长变更联动告警", () => {
  const tpl = {
    id: 2,
    name: "晚间全量冒烟",
    smoke_minutes: 60,
    analysis_minutes: 30,
    description: ""
  };

  /** 打开编辑弹窗并点保存，返回 footer 保存按钮 */
  async function openEditAndSave() {
    // el-table 行渲染是异步的：mount 后先 flush 一拍再找行内「编辑」按钮
    await flushPromises();
    await wrapper
      .findAll("button")
      .find(b => b.text().includes("编辑"))!
      .trigger("click");
    await flushPromises();
    const save = saveButton(wrapper);
    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await flushPromises();
    return save;
  }

  it("编辑保存响应带非空 warnings：ElMessage.warning 汇总重叠策略对", async () => {
    const warningSpy = vi
      .spyOn(ElMessage, "warning")
      .mockImplementation(() => ({}) as never);
    updateTemplateMock.mockResolvedValue({
      warnings: [
        {
          branch: "TR5",
          first: "27A-TR5-晚间全量",
          second: "27A-TR5-晨间构建",
          overlap_start: "22:00",
          overlap_end: "23:30"
        },
        {
          branch: "TR6",
          first: "27A-TR6-甲",
          second: "27A-TR6-乙",
          overlap_start: "01:00",
          overlap_end: "02:00"
        }
      ]
    } as never);
    wrapper = mount(TemplatesTab, { props: { templates: [tpl] } });
    await openEditAndSave();

    expect(updateTemplateMock).toHaveBeenCalledTimes(1);
    expect(warningSpy).toHaveBeenCalledTimes(1);
    const arg = warningSpy.mock.calls[0][0] as { message: string };
    expect(arg.message).toContain("模板时长变更导致 2 组启用策略阶段重叠：");
    expect(arg.message).toContain("TR5 27A-TR5-晚间全量×27A-TR5-晨间构建");
    expect(arg.message).toContain("TR6 27A-TR6-甲×27A-TR6-乙");
  });

  it("响应无 warnings 字段（未改时长）：不弹告警", async () => {
    const warningSpy = vi
      .spyOn(ElMessage, "warning")
      .mockImplementation(() => ({}) as never);
    updateTemplateMock.mockResolvedValue({} as never);
    wrapper = mount(TemplatesTab, { props: { templates: [tpl] } });
    await openEditAndSave();

    expect(updateTemplateMock).toHaveBeenCalledTimes(1);
    expect(warningSpy).not.toHaveBeenCalled();
    expect(wrapper.emitted("refresh")).toBeTruthy();
  });

  it("warnings 为空数组（无重叠）：不弹告警", async () => {
    const warningSpy = vi
      .spyOn(ElMessage, "warning")
      .mockImplementation(() => ({}) as never);
    updateTemplateMock.mockResolvedValue({ warnings: [] } as never);
    wrapper = mount(TemplatesTab, { props: { templates: [tpl] } });
    await openEditAndSave();

    expect(warningSpy).not.toHaveBeenCalled();
  });
});

describe("R4-F3 TemplatesTab 保存在途守卫", () => {
  it("请求在途时保存按钮呈 loading，双击仅发一次 create", async () => {
    const { promise, resolveFn } =
      pendingCreate<Awaited<ReturnType<typeof adminApi.createTemplate>>>();
    createTemplateMock.mockReturnValue(promise);
    wrapper = mount(TemplatesTab, { props: { templates: [] } });

    await wrapper
      .findAll("button")
      .find(b => b.text().includes("新增模板"))!
      .trigger("click");
    await flushPromises();

    // 第一个表单项为模板名称（必填）
    const items = formItems(wrapper);
    setInput(
      items[0].find("input").element as HTMLInputElement,
      "晚间全量冒烟"
    );
    await nextTick();

    const save = saveButton(wrapper);
    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await nextTick();
    expect(createTemplateMock).toHaveBeenCalledTimes(1);
    expect(save.classList.contains("is-loading")).toBe(true);

    save.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    await nextTick();
    expect(createTemplateMock).toHaveBeenCalledTimes(1);

    resolveFn({} as Awaited<ReturnType<typeof adminApi.createTemplate>>);
    await flushPromises();
    expect(save.classList.contains("is-loading")).toBe(false);
    expect(wrapper.emitted("refresh")).toBeTruthy();
  });
});
