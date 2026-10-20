// API 层契约测试：mock http 实例，锁定各 API 函数的 URL / 方法 / 参数拼装
import { beforeEach, describe, expect, it, vi } from "vitest";

const httpMock = vi.hoisted(() => ({
  get: vi.fn().mockResolvedValue([]),
  post: vi.fn().mockResolvedValue({}),
  put: vi.fn().mockResolvedValue({}),
  patch: vi.fn().mockResolvedValue({}),
  delete: vi.fn().mockResolvedValue({})
}));

vi.mock("@/api/http", () => ({ default: httpMock }));

import {
  createStrategy,
  getStrategies,
  previewStrategy,
  toggleStrategy,
  updateStrategy
} from "@/api/strategy";
import { getPlan } from "@/api/plan";

describe("api/strategy 契约", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("getStrategies 携带查询参数", async () => {
    await getStrategies({ version_id: 3 });
    expect(httpMock.get).toHaveBeenCalledWith("/strategies", {
      params: { version_id: 3 }
    });
  });

  it("previewStrategy POST /strategies/preview", async () => {
    const form = {
      branch_id: 1,
      template_id: 2,
      name: "s",
      build_start_time: "22:00",
      push_mode: "normal" as const,
      enabled: true
    };
    await previewStrategy(form);
    expect(httpMock.post).toHaveBeenCalledWith("/strategies/preview", form);
  });

  it("create/update/toggle 的方法与路径", async () => {
    const form = {
      branch_id: 1,
      template_id: 2,
      name: "s",
      build_start_time: "22:00",
      push_mode: "normal" as const,
      enabled: true
    };
    await createStrategy(form);
    expect(httpMock.post).toHaveBeenCalledWith("/strategies", form);
    await updateStrategy(9, form);
    expect(httpMock.patch).toHaveBeenCalledWith("/strategies/9", form);
    // 后端 toggle 为无参翻转语义：不再发送会被忽略的 enabled 参数
    await toggleStrategy(9);
    expect(httpMock.patch).toHaveBeenCalledWith("/strategies/9/toggle");
  });
});

describe("api/plan 契约", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("getPlan 传递 date 与 version_id", async () => {
    await getPlan({ date: "2026-10-11", version_id: 5 });
    expect(httpMock.get).toHaveBeenCalledWith("/plan", {
      params: { date: "2026-10-11", version_id: 5 }
    });
  });
});
