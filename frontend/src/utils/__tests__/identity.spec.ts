// utils/identity 单测（R5 补测试基建）：启动时业务身份快照刷新
// 锁定三条语义：无 token 不发请求；接口失败永不 reject（静默）；成功回写
// localStorage 快照与 user store（角色/昵称与登录写入口径一致）
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/auth", () => ({ getMe: vi.fn() }));
vi.mock("@/utils/auth", () => ({
  getToken: vi.fn(),
  // 基座副本键名与真实模块一致（R7-F5：基座 user-info roles 同步）
  userKey: "user-info"
}));
// user store 桩：三个 SET_* 动作由断言检查（真实模块依赖 pinia 实例，单测不拉起）
const storeStub = {
  SET_USERNAME: vi.fn(),
  SET_NICKNAME: vi.fn(),
  SET_ROLES: vi.fn()
};
vi.mock("@/store/modules/user", () => ({
  useUserStoreHook: () => storeStub
}));

import { getMe } from "@/api/auth";
import { getToken } from "@/utils/auth";
import { businessUserKey } from "@/store/constants";
import { refreshBusinessUser } from "@/utils/identity";
import type { UserInfo } from "@/api/types";

const getMeMock = vi.mocked(getMe);
const getTokenMock = vi.mocked(getToken);

const ME = {
  id: 5,
  username: "pm27a",
  display_name: "27A负责人",
  role: "pm",
  bound_version_id: 1,
  bound_version_name: "27A"
} as UserInfo;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  // restoreMocks 会清掉桩动作的实现记录：无需重建（纯 vi.fn 断言调用即可）
});

afterEach(() => {
  localStorage.clear();
});

describe("refreshBusinessUser 启动身份快照刷新", () => {
  it("无 token：不发请求、不写快照", async () => {
    getTokenMock.mockReturnValue({} as never);
    await refreshBusinessUser();
    expect(getMeMock).not.toHaveBeenCalled();
    expect(localStorage.getItem(businessUserKey)).toBeNull();
    expect(storeStub.SET_USERNAME).not.toHaveBeenCalled();
  });

  it("token 缺失（getToken 返回 null 形态）：同样不发请求", async () => {
    getTokenMock.mockReturnValue(null as never);
    await refreshBusinessUser();
    expect(getMeMock).not.toHaveBeenCalled();
  });

  it("接口失败：永不 reject（静默），不写快照、不动 store", async () => {
    getTokenMock.mockReturnValue({ accessToken: "t" } as never);
    getMeMock.mockRejectedValue(new Error("network down"));
    await expect(refreshBusinessUser()).resolves.toBeUndefined();
    expect(getMeMock).toHaveBeenCalledTimes(1);
    // 请求级 silent：轮询/启动刷新不弹全局 toast 的口径
    expect(getMeMock).toHaveBeenCalledWith({ silent: true });
    expect(localStorage.getItem(businessUserKey)).toBeNull();
    expect(storeStub.SET_ROLES).not.toHaveBeenCalled();
  });

  it("成功：回写 localStorage 快照并同步 user store（用户名/昵称/角色）", async () => {
    getTokenMock.mockReturnValue({ accessToken: "t" } as never);
    getMeMock.mockResolvedValue(ME);
    await refreshBusinessUser();

    // localStorage 快照：与登录写入同款 JSON 序列化
    expect(JSON.parse(localStorage.getItem(businessUserKey)!)).toEqual(ME);
    // store 同步：角色写入为数组口径（与登录时一致，供菜单/路由过滤）
    expect(storeStub.SET_USERNAME).toHaveBeenCalledWith("pm27a");
    expect(storeStub.SET_NICKNAME).toHaveBeenCalledWith("27A负责人");
    expect(storeStub.SET_ROLES).toHaveBeenCalledWith(["pm"]);
  });

  it("成功且基座 user-info 存在：同步其 roles 字段并保留其余字段（R7-F5）", async () => {
    getTokenMock.mockReturnValue({ accessToken: "t" } as never);
    getMeMock.mockResolvedValue(ME);
    // 登录时写入的基座副本：旧角色 admin，含 expires 等登录字段
    localStorage.setItem(
      "user-info",
      JSON.stringify({
        username: "pm27a",
        expires: 1790000000000,
        roles: ["admin"],
        permissions: ["*:*:*"]
      })
    );
    await refreshBusinessUser();
    const base = JSON.parse(localStorage.getItem("user-info")!);
    expect(base.roles).toEqual(["pm"]);
    expect(base.username).toBe("pm27a");
    expect(base.expires).toBe(1790000000000);
    expect(base.permissions).toEqual(["*:*:*"]);
  });

  it("成功但基座 user-info 不存在（登录流程未完成）：跳过同步不构造", async () => {
    getTokenMock.mockReturnValue({ accessToken: "t" } as never);
    getMeMock.mockResolvedValue(ME);
    await expect(refreshBusinessUser()).resolves.toBeUndefined();
    expect(localStorage.getItem("user-info")).toBeNull();
    expect(JSON.parse(localStorage.getItem(businessUserKey)!)).toEqual(ME);
  });
});
