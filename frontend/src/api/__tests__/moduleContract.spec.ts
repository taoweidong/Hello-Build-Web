// API 模块契约测试：mock http 实例，锁定各 API 函数的 URL / 方法 / 参数拼装
// （与后端 urls.py 对照）
// 2026-10-20 页面精简：admin（仅保留模板只读）/ logs / branchConfig 契约随页面下线删除，
// 本文件覆盖 admin.templates / weekly / auth / borrowFlow / slotBooking。
import { beforeEach, describe, expect, it, vi } from "vitest";

const httpMock = vi.hoisted(() => ({
  get: vi.fn().mockResolvedValue([]),
  post: vi.fn().mockResolvedValue({}),
  put: vi.fn().mockResolvedValue({}),
  patch: vi.fn().mockResolvedValue({}),
  delete: vi.fn().mockResolvedValue({})
}));

vi.mock("@/api/http", () => ({ default: httpMock }));

import { adminApi } from "@/api/admin";
import { getWeekly } from "@/api/weekly";
import { getMe, loginApi, logoutApi } from "@/api/auth";
import {
  approveBorrowFlow,
  cancelBorrowFlow,
  createBorrowFlow,
  listBorrowFlows,
  rejectBorrowFlow
} from "@/api/borrowFlow";
import {
  createBooking,
  getMyBookings,
  getSlotCalendar,
  releaseBooking,
  rescheduleBooking
} from "@/api/slotBooking";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("api/admin 契约（仅模板只读端点）", () => {
  it("模板列表", async () => {
    await adminApi.getTemplates();
    expect(httpMock.get).toHaveBeenCalledWith("/admin/templates");
  });
});

describe("api/weekly 契约", () => {
  it("week_start/version_id 透传", async () => {
    await getWeekly({ week_start: "2026-10-12", version_id: 3 });
    expect(httpMock.get).toHaveBeenCalledWith("/weekly", {
      params: { week_start: "2026-10-12", version_id: 3 }
    });
  });
});

describe("api/auth 契约", () => {
  it("登录/登出/当前用户", async () => {
    await loginApi({ username: "u", password: "p" });
    expect(httpMock.post).toHaveBeenCalledWith("/auth/login", {
      username: "u",
      password: "p"
    });
    await logoutApi();
    // 登出必须携带 silent：失败不弹 toast（本地清理照常）
    expect(httpMock.post).toHaveBeenCalledWith("/auth/logout", null, {
      silent: true
    });
    await getMe();
    expect(httpMock.get).toHaveBeenCalledWith("/auth/me", undefined);
  });

  it("getMe 透传请求级配置（启动静默刷新用 silent: true，R3-F10）", async () => {
    await getMe({ silent: true });
    expect(httpMock.get).toHaveBeenCalledWith("/auth/me", { silent: true });
  });
});

describe("api/borrowFlow 契约", () => {
  it("列表状态过滤参数拼装", async () => {
    await listBorrowFlows();
    expect(httpMock.get).toHaveBeenCalledWith("/borrow-flows", {
      params: {}
    });
    await listBorrowFlows("pending");
    expect(httpMock.get).toHaveBeenCalledWith("/borrow-flows", {
      params: { status: "pending" }
    });
  });

  it("发起/审批/驳回/撤销", async () => {
    const form = {
      strategy_id: 1,
      target_branch_id: 2,
      new_build_time: "23:00",
      reason: "r"
    };
    await createBorrowFlow(form);
    expect(httpMock.post).toHaveBeenCalledWith("/borrow-flows", form);
    await approveBorrowFlow(5);
    expect(httpMock.post).toHaveBeenCalledWith("/borrow-flows/5/approve");
    await rejectBorrowFlow(5, "不行");
    expect(httpMock.post).toHaveBeenCalledWith("/borrow-flows/5/reject", {
      comment: "不行"
    });
    await cancelBorrowFlow(5);
    expect(httpMock.post).toHaveBeenCalledWith("/borrow-flows/5/cancel");
  });
});

describe("api/slotBooking 契约", () => {
  it("日历", async () => {
    await getSlotCalendar("2026-10");
    expect(httpMock.get).toHaveBeenCalledWith("/slot-calendar", {
      params: { month: "2026-10" }
    });
  });

  it("抢占/释放/改期/我的抢占分页", async () => {
    const payload = {
      date: "2026-10-12",
      template_id: 1,
      purpose: "联调占用",
      version_id: 2,
      branch_id: 3
    };
    await createBooking(payload);
    expect(httpMock.post).toHaveBeenCalledWith("/slot-bookings", payload);
    await releaseBooking(5, "临时会议");
    expect(httpMock.post).toHaveBeenCalledWith("/slot-bookings/5/release", {
      release_reason: "临时会议"
    });
    await rescheduleBooking(5, { date: "2026-10-13", template_id: 2 });
    expect(httpMock.patch).toHaveBeenCalledWith("/slot-bookings/5", {
      date: "2026-10-13",
      template_id: 2
    });
    await getMyBookings(2, 10);
    expect(httpMock.get).toHaveBeenCalledWith("/slot-bookings/mine", {
      params: { page: 2, page_size: 10 }
    });
  });
});
