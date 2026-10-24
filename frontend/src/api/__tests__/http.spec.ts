// http.ts 拦截器单测：通过自定义 axios adapter 模拟传输层，验证统一契约行为
import { describe, expect, it, vi, beforeEach } from "vitest";

const { elMessageError, elMessageBoxAlert, removeTokenMock } = vi.hoisted(
  () => ({
    elMessageError: vi.fn(),
    elMessageBoxAlert: vi.fn(),
    removeTokenMock: vi.fn()
  })
);

vi.mock("element-plus", () => ({
  ElMessage: { error: elMessageError, success: vi.fn() },
  ElMessageBox: { alert: elMessageBoxAlert }
}));

vi.mock("@/utils/auth", () => ({
  getToken: vi.fn(() => ({ accessToken: "test-token" })),
  removeToken: removeTokenMock
}));

import service, { BizError } from "@/api/http";

type Adapter = (
  config: Record<string, unknown>
) => Promise<Record<string, unknown>>;

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
    // vi.fn() 计数跨用例累计（restoreMocks 只还原 spyOn），显式清零隔离
    removeTokenMock.mockClear();
    elMessageError.mockClear();
    elMessageBoxAlert.mockClear();
  });

  it("成功响应解包 data 字段", async () => {
    useAdapter(async () => ({
      data: { code: 0, message: "ok", data: { hello: 1 } }
    }));
    const data = await service.get("/demo");
    expect(data).toEqual({ hello: 1 });
  });

  it("HTTP 200 但业务码非 0 → reject BizError 并弹错", async () => {
    useAdapter(async () => ({
      data: { code: 42201, message: "参数非法", data: null }
    }));
    await expect(service.get("/demo")).rejects.toMatchObject({
      name: "BizError",
      code: 42201,
      message: "参数非法"
    });
    await expect(service.get("/demo")).rejects.toBeInstanceOf(BizError);
    expect(elMessageError).toHaveBeenCalledWith("参数非法");
  });

  it("HTTP 401 + 40100 → 清理 token 与业务用户信息并跳登录", async () => {
    localStorage.setItem(
      "build-user-info",
      JSON.stringify({ username: "old" })
    );
    useAdapter(httpErrorAdapter(401, { code: 40100, message: "未认证" }));
    await expect(service.get("/demo")).rejects.toMatchObject({ code: 40100 });
    expect(removeTokenMock).toHaveBeenCalled();
    expect(localStorage.getItem("build-user-info")).toBeNull();
    expect(window.location.hash).toBe("#/login");
  });

  it("401 跳转 URL 走 appHashUrl 唯一来源：含 origin 与部署子路径（R4-F12）", async () => {
    useAdapter(httpErrorAdapter(401, { code: 40100, message: "未认证" }));
    await expect(service.get("/demo")).rejects.toMatchObject({ code: 40100 });
    // 与 utils/appUrl.appHashUrl 同款拼法（origin + pathname + #/login），
    // 不再手拼 `${pathname}#/login` 丢 origin
    const { origin, pathname } = window.location;
    expect(window.location.href).toBe(`${origin}${pathname}#/login`);
  });

  it("40101 凭据错误 → 弹真实文案，不清理 token、不跳转（R7-F2：与 40100 拆分）", async () => {
    localStorage.setItem(
      "build-user-info",
      JSON.stringify({ username: "old" })
    );
    window.location.hash = "#/strategy"; // 预置非登录页锚点，若误跳转会被改写
    useAdapter(
      httpErrorAdapter(401, { code: 40101, message: "用户名或密码错误" })
    );
    await expect(service.get("/demo")).rejects.toMatchObject({ code: 40101 });
    // 登录失败不是登录态失效：不清 token（登录页本就未持有有效会话）、不跳转
    expect(removeTokenMock).not.toHaveBeenCalled();
    expect(elMessageError).toHaveBeenCalledWith("用户名或密码错误");
    expect(window.location.hash).toBe("#/strategy");
  });

  it("40100 已指向登录页时跳过重复赋值（R7-F13：并发 401 不重复导航）", async () => {
    window.location.hash = "#/login"; // 预置已在登录页
    useAdapter(httpErrorAdapter(401, { code: 40100, message: "未认证" }));
    await expect(service.get("/demo")).rejects.toMatchObject({ code: 40100 });
    expect(removeTokenMock).toHaveBeenCalled();
    expect(localStorage.getItem("build-user-info")).toBeNull();
    // href 已是登录页：不重复赋值（无重载排队），保持登录页
    const { origin, pathname } = window.location;
    expect(window.location.href).toBe(`${origin}${pathname}#/login`);
  });

  it("非信封 200 响应（裸数组）→ 原样透传，不误判业务失败（R7-F13）", async () => {
    useAdapter(async () => ({ data: [1, 2, 3] }));
    const data = await service.get("/demo");
    expect(data).toEqual([1, 2, 3]);
    expect(elMessageError).not.toHaveBeenCalled();
  });

  it("非信封 200 响应（HTML 网关错误页字符串）→ 原样透传（R7-F13）", async () => {
    useAdapter(async () => ({ data: "<html>Gateway Error</html>" }));
    const data = await service.get("/demo");
    expect(data).toBe("<html>Gateway Error</html>");
    expect(elMessageError).not.toHaveBeenCalled();
  });

  it("请求取消 → 静默 reject BizError(-1)，不弹 toast（R7-F13）", async () => {
    elMessageError.mockClear();
    (service.defaults as any).adapter = async (config: any) => {
      // 与 axios.CanceledError 同构：isCancel 按 __CANCEL__ 标记判定
      const error = new Error("canceled") as any;
      error.__CANCEL__ = true;
      error.code = "ERR_CANCELED";
      error.config = config;
      throw error;
    };
    await expect(service.get("/demo")).rejects.toMatchObject({
      code: -1,
      message: "请求已取消"
    });
    expect(elMessageError).not.toHaveBeenCalled();
  });

  it("silent + 401 组合：静默请求也必须跳登录，但不弹 toast", async () => {
    elMessageError.mockClear();
    localStorage.setItem(
      "build-user-info",
      JSON.stringify({ username: "old" })
    );
    useAdapter(httpErrorAdapter(401, { code: 40100, message: "未认证" }));
    await expect(service.get("/demo", { silent: true })).rejects.toMatchObject({
      code: 40100
    });
    expect(removeTokenMock).toHaveBeenCalled();
    expect(localStorage.getItem("build-user-info")).toBeNull();
    expect(window.location.hash).toContain("login");
    expect(elMessageError).not.toHaveBeenCalled();
  });

  it("40301 → 无权限提示", async () => {
    useAdapter(
      httpErrorAdapter(403, { code: 40301, message: "仅管理员可操作" })
    );
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
    useAdapter(
      httpErrorAdapter(409, { code: 40902, message: "该版本下分支已存在" })
    );
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

  it("silent 配置：失败不弹全局提示但仍 reject BizError（轮询用）", async () => {
    elMessageError.mockClear();
    useAdapter(httpErrorAdapter(500, { code: 50000, message: "内部错误" }));
    await expect(service.get("/demo", { silent: true })).rejects.toMatchObject({
      code: 50000
    });
    expect(elMessageError).not.toHaveBeenCalled();
  });

  it("网络层错误（无业务码）→ BizError 兜底 code -1，不与成功语义 0 冲突", async () => {
    (service.defaults as any).adapter = async (config: any) => {
      const error = new Error("Network Error") as any;
      error.config = config;
      throw error;
    };
    await expect(service.get("/demo", { silent: true })).rejects.toMatchObject({
      code: -1
    });
  });
});
