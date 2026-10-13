// 分支配置页组件级测试
// 背景：2026-10-13 全量巡检发现 loadBranches 自页面诞生起无任何调用点，
// 接口 200 有数据、页面恒显「暂无分支」。本 spec 锁定首屏加载行为防回归。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import type { VueWrapper } from "@vue/test-utils";

vi.mock("@/api/branchConfig", () => ({
  addBranchPermission: vi.fn(),
  addBranchProject: vi.fn(),
  createBranch: vi.fn(),
  getBranches: vi.fn(),
  getBranchConfig: vi.fn(),
  getBranchInstances: vi.fn(),
  getUsersAll: vi.fn().mockResolvedValue([]),
  removeBranchPermission: vi.fn(),
  removeBranchProject: vi.fn(),
  startBranchProject: vi.fn(),
  stopBranchProject: vi.fn(),
  updateStartupConfig: vi.fn()
}));
vi.mock("@/api/plan", () => ({ getPlan: vi.fn() }));

import {
  getBranches,
  getBranchConfig,
  getBranchInstances,
  type BranchConfigResponse,
  type BranchItem
} from "@/api/branchConfig";
import BranchConfigPage from "../index.vue";

const branchesMock = vi.mocked(getBranches);
const configMock = vi.mocked(getBranchConfig);
const instancesMock = vi.mocked(getBranchInstances);

const BRANCH_1: BranchItem = {
  id: 1,
  version_id: 1,
  version_name: "27A",
  name: "master",
  repository_url: "",
  description: ""
};
const BRANCH_2: BranchItem = {
  id: 2,
  version_id: 1,
  version_name: "27A",
  name: "TR5",
  repository_url: "https://example.com/repo.git",
  description: ""
};

function makeConfig(id: number): BranchConfigResponse {
  return {
    branch: { ...BRANCH_1, id },
    branch_projects: [],
    permissions: [{ id: 1, user_id: 1, username: "admin", role: "ADMIN" }],
    my_role: "ADMIN",
    available_users: [],
    available_projects: []
  };
}

let wrapper: VueWrapper;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  localStorage.setItem(
    "build-user-info",
    JSON.stringify({ id: 1, username: "admin", role: "admin" })
  );
  branchesMock.mockResolvedValue([BRANCH_1, BRANCH_2]);
  configMock.mockImplementation(async id => makeConfig(id));
  instancesMock.mockResolvedValue([]);
});

afterEach(() => {
  wrapper?.unmount();
});

describe("分支配置页首屏加载", () => {
  it("挂载即拉分支列表并渲染（回归：loadBranches 曾无调用点，页面恒显暂无分支）", async () => {
    wrapper = mount(BranchConfigPage);
    await flushPromises();

    expect(branchesMock).toHaveBeenCalledTimes(1);
    const items = wrapper.findAll(".branch-item");
    expect(items).toHaveLength(2);
    expect(items[0].text()).toContain("27A / master");
    // 左侧列表区不再有「暂无分支」空态（子面板自身的空态不在本断言范围）
    expect(wrapper.find(".branch-side").text()).not.toContain("暂无分支");
  });

  it("默认选中首个分支并加载其聚合配置", async () => {
    wrapper = mount(BranchConfigPage);
    await flushPromises();

    expect(configMock).toHaveBeenCalledWith(BRANCH_1.id);
    expect(wrapper.find(".branch-item.active").text()).toContain("master");
  });

  it("接口失败时列表清空回退空态，不残留旧数据", async () => {
    wrapper = mount(BranchConfigPage);
    await flushPromises();
    expect(wrapper.findAll(".branch-item")).toHaveLength(2);

    branchesMock.mockRejectedValueOnce(new Error("网络故障"));
    // 通过再次触发加载来验证失败分支：点搜索清空再手动重挂载
    wrapper.unmount();
    branchesMock.mockRejectedValue(new Error("网络故障"));
    wrapper = mount(BranchConfigPage);
    await flushPromises();

    expect(wrapper.findAll(".branch-item")).toHaveLength(0);
    expect(wrapper.text()).toContain("暂无分支");
  });
});
