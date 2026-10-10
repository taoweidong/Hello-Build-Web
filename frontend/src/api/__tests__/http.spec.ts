// http.ts 拦截器单测：通过自定义 axios adapter 模拟传输层，验证统一契约行为
import { describe, expect, it, vi, beforeEach } from "vitest";

const { elMessageError, elMessageBoxAlert, removeTokenMock } = vi.hoisted(() => ({
  elMessageError: vi.fn(),
  elMessageBoxAlert: vi.fn(),
  removeTokenMock: vi.fn()
}));

vi.mock("element-plus", () => ({
  ElMessage: { error: elMessageError, success: vi.fn() },
  ElMessageBox: { alert: elMessageBoxAlert }
}));

vi.mock("@/utils/auth", () => ({
  getToken: vi.fn(() => ({ accessToken: "test-token" })),
  removeToken: removeTokenMock
}));

import service, { BizError } from "@/api/http";

type Adapter = (config: Record<string, unknown>) => Promise<Record<string, unknown>>;

function useAdapter(adapter: Adapter) {
  // axios 实例级 adapter 替换：拦截器照常执行，仅伪造传输层
  (service.defaults as any).adapter = async (config: any) => {
    const res = await adapter(config);
    return {
      data: res.data,
      status: res.status ?? 200,
      statusText: "OK",
      headers: {},
      config,
      request: {}
    };
  };
}

function httpErrorAdapter(status: number, body: unknown): Adapter {
  return async config => {
    const error = new Error("Request failed") as any;
    error.response = { status, data: body, config, headers: {} };
    error.config = config;
    throw error;
  };
}

describe("api/http 拦截器", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("成功响应解包 data 字段", async () => {
    useAdapter(async () => ({ data: { code: 0, message: "ok", data: { hello: 1 } } }));
    const data = await service.get("/demo");
    expect(data).toEqual({ hello: 1 });
  });

  it("HTTP 200 但业务码非 0 → reject BizError 并弹错", async () => {
    useAdapter(async () => ({ data: { code: 42201, message: "参数非法", data: null } }));
    await expect(service.get("/demo")).rejects.toMatchObject({
      name: "BizError",
      code: 42201,
      message: "参数非法"
    });
    await expect(service.get("/demo")).rejects.toBeInstanceOf(BizError);
    expect(elMessageError).toHaveBeenCalledWith("参数非法");
  });

  it("HTTP 401 + 40100 → 清理 token 与业务用户信息并跳登录", async () => {
    localStorage.setItem("build-user-info", JSON.stringify({ username: "old" }));
    useAdapter(httpErrorAdapter(401, { code: 40100, message: "未认证" }));
    await expect(service.get("/demo")).rejects.toMatchObject({ code: 40100 });
    expect(removeTokenMock).toHaveBeenCalled();
    expect(localStorage.getItem("build-user-info")).toBeNull();
    expect(window.location.hash).toContain("login");
  });

  it("40301 → 无权限提示", async () => {
    useAdapter(httpErrorAdapter(403, { code: 40301, message: "仅管理员可操作" }));
    await expect(service.get("/demo")).rejects.toMatchObject({ code: 40301 });
    expect(elMessageError).toHaveBeenCalledWith("仅管理员可操作");
  });

  it("40901 → 策略冲突专用弹框", async () => {
    useAdapter(httpErrorAdapter(409, { code: 40901, message: "阶段时间冲突" }));
    await expect(service.get("/demo")).rejects.toMatchObject({ code: 40901 });
    expect(elMessageBoxAlert).toHaveBeenCalledWith(
      "阶段时间冲突",
      "策略时间冲突",
      expect.objectContaining({ type: "error" })
    );
  });

  it("40902 → 错误提示走 ElMessage（不再写死报告文案）", async () => {
    useAdapter(httpErrorAdapter(409, { code: 40902, message: "该版本下分支已存在" }));
    await expect(service.get("/demo")).rejects.toMatchObject({ code: 40902 });
    expect(elMessageError).toHaveBeenCalledWith("该版本下分支已存在");
  });

  it("未知错误码 → 通用提示，reject BizError 携带 httpStatus", async () => {
    useAdapter(httpErrorAdapter(500, { code: 40401, message: "不存在" }));
    await expect(service.get("/demo")).rejects.toMatchObject({
      code: 40401,
      httpStatus: 500
    });
    expect(elMessageError).toHaveBeenCalledWith("不存在");
  });
});
