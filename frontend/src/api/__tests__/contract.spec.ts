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
import {
  createReport,
  getReport,
  getReports,
  getReportRevisions,
  publishReport,
  updateReport
} from "@/api/report";

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
      push_mode: "normal",
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
      push_mode: "normal",
      enabled: true
    };
    await createStrategy(form);
    expect(httpMock.post).toHaveBeenCalledWith("/strategies", form);
    await updateStrategy(9, form);
    expect(httpMock.patch).toHaveBeenCalledWith("/strategies/9", form);
    await toggleStrategy(9, true);
    expect(httpMock.patch).toHaveBeenCalledWith("/strategies/9/toggle", null, {
      params: { enabled: true }
    });
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

describe("api/report 契约", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("列表/详情/新建/更新", async () => {
    await getReports({ status: "draft", keyword: "27A" });
    expect(httpMock.get).toHaveBeenCalledWith("/reports", {
      params: { status: "draft", keyword: "27A" }
    });
    await getReport(7);
    expect(httpMock.get).toHaveBeenCalledWith("/reports/7");
    const form = { title: "t", conclusion: "pass", summary: "s" };
    await createReport(form);
    expect(httpMock.post).toHaveBeenCalledWith("/reports", form);
    await updateReport(7, form);
    expect(httpMock.put).toHaveBeenCalledWith("/reports/7", form);
  });

  it("发布携带截图、修改记录路径", async () => {
    await publishReport(7, "data:image/png;base64,AAA");
    expect(httpMock.post).toHaveBeenCalledWith("/reports/7/publish", {
      screenshot: "data:image/png;base64,AAA"
    });
    await getReportRevisions(7);
    expect(httpMock.get).toHaveBeenCalledWith("/reports/7/revisions");
  });
});
