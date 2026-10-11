// API 模块契约测试（第二批）：admin/logs/weekly/auth/borrowFlow/branchConfig/slotBooking
// mock http 实例，锁定各 API 函数的 URL / 方法 / 参数拼装（与后端 urls.py 对照）
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
import { logsApi } from "@/api/logs";
import { getWeekly } from "@/api/weekly";
import { getMe, loginApi, logoutApi } from "@/api/auth";
import {
  approveBorrowFlow,
  borrowFlowUrl,
  createBorrowFlow,
  listBorrowFlows,
  rejectBorrowFlow
} from "@/api/borrowFlow";
import {
  addBranchPermission,
  addBranchProject,
  createBranch,
  createProject,
  deleteBranch,
  getBranchConfig,
  getBranches,
  getBranchInstances,
  getProjects,
  getUsersAll,
  removeBranchPermission,
  removeBranchProject,
  startBranchProject,
  stopBranchProject,
  updateStartupConfig
} from "@/api/branchConfig";
import {
  createBooking,
  deleteSlotTemplate,
  getMyBookings,
  getSlotBookings,
  getSlotCalendar,
  getSlotTemplates,
  releaseBooking
} from "@/api/slotBooking";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("api/admin 契约", () => {
  it("版本与分支", async () => {
    await adminApi.getVersions();
    expect(httpMock.get).toHaveBeenCalledWith("/admin/versions");
    await adminApi.createVersion({ name: "28A", pm_user_id: 3 });
    expect(httpMock.post).toHaveBeenCalledWith("/admin/versions", {
      name: "28A",
      pm_user_id: 3
    });
    await adminApi.updateVersion(1, { status: "archived" });
    expect(httpMock.patch).toHaveBeenCalledWith("/admin/versions/1", {
      status: "archived"
    });
    await adminApi.addBranch(1, "TR6");
    expect(httpMock.post).toHaveBeenCalledWith("/admin/versions/1/branches", {
      name: "TR6"
    });
  });

  it("用户管理", async () => {
    await adminApi.getUsers();
    expect(httpMock.get).toHaveBeenCalledWith("/admin/users");
    await adminApi.createUser({
      username: "u",
      password: "p",
      role: "builder"
    });
    expect(httpMock.post).toHaveBeenCalledWith("/admin/users", {
      username: "u",
      password: "p",
      role: "builder"
    });
    await adminApi.updateUser(2, { is_active: false });
    expect(httpMock.patch).toHaveBeenCalledWith("/admin/users/2", {
      is_active: false
    });
  });

  it("模板与配置", async () => {
    await adminApi.getTemplates();
    expect(httpMock.get).toHaveBeenCalledWith("/admin/templates");
    await adminApi.deleteTemplate(4);
    expect(httpMock.delete).toHaveBeenCalledWith("/admin/templates/4");
    await adminApi.getConfig();
    expect(httpMock.get).toHaveBeenCalledWith("/admin/config");
    const cfg = { build_minutes: 90, push_minutes: 30, sync_buffer_minutes: 10 };
    await adminApi.updateConfig(cfg);
    expect(httpMock.put).toHaveBeenCalledWith("/admin/config", cfg);
  });

  it("策略管理（toggle 为无参翻转 PATCH）", async () => {
    await adminApi.getAdminStrategies({ version_id: 2 });
    expect(httpMock.get).toHaveBeenCalledWith("/admin/strategies", {
      params: { version_id: 2 }
    });
    await adminApi.toggleAdminStrategy(8);
    expect(httpMock.patch).toHaveBeenCalledWith("/admin/strategies/8/toggle");
    await adminApi.deleteAdminStrategy(8);
    expect(httpMock.delete).toHaveBeenCalledWith("/admin/strategies/8");
  });
});

describe("api/logs 契约", () => {
  it("四类日志端点与参数", async () => {
    await logsApi.execution({ date: "2026-10-12", version_id: 1 });
    expect(httpMock.get).toHaveBeenCalledWith("/logs/execution", {
      params: { date: "2026-10-12", version_id: 1 }
    });
    await logsApi.changes({ from: "a", to: "b" });
    expect(httpMock.get).toHaveBeenCalledWith("/logs/changes", {
      params: { from: "a", to: "b" }
    });
    await logsApi.operations({});
    expect(httpMock.get).toHaveBeenCalledWith("/admin/logs/operations", {
      params: {}
    });
    await logsApi.security({});
    expect(httpMock.get).toHaveBeenCalledWith("/admin/logs/security", {
      params: {}
    });
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
    expect(httpMock.get).toHaveBeenCalledWith("/auth/me");
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

  it("发起/审批/驳回", async () => {
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
  });

  it("直达链接为 hash 路由且含 focus 参数", () => {
    const url = borrowFlowUrl(9);
    expect(url).toContain("#/borrow-flow/index?focus=9");
    expect(url.startsWith(window.location.origin)).toBe(true);
  });
});

describe("api/branchConfig 契约", () => {
  it("分支与聚合配置", async () => {
    await getBranches();
    expect(httpMock.get).toHaveBeenCalledWith("/branches");
    await createBranch({ version_id: 1, name: "master" });
    expect(httpMock.post).toHaveBeenCalledWith("/branches", {
      version_id: 1,
      name: "master"
    });
    await deleteBranch(3);
    expect(httpMock.delete).toHaveBeenCalledWith("/branches/3");
    await getBranchConfig(3);
    expect(httpMock.get).toHaveBeenCalledWith("/branches/3/config");
  });

  it("工程关联/启动参数/授权", async () => {
    await addBranchProject(3, { project_id: 7 });
    expect(httpMock.post).toHaveBeenCalledWith("/branches/3/projects", {
      project_id: 7
    });
    await removeBranchProject(11);
    expect(httpMock.delete).toHaveBeenCalledWith("/branch-projects/11");
    await updateStartupConfig(11, { build_job_name: "job" } as never);
    expect(httpMock.put).toHaveBeenCalledWith("/branch-projects/11/config", {
      build_job_name: "job"
    });
    await addBranchPermission(3, { user_id: 5, role: "OPERATOR" });
    expect(httpMock.post).toHaveBeenCalledWith("/branches/3/permissions", {
      user_id: 5,
      role: "OPERATOR"
    });
    await removeBranchPermission(13);
    expect(httpMock.delete).toHaveBeenCalledWith("/branch-permissions/13");
  });

  it("用户/工程库/实例（实例请求透传 silent 配置）", async () => {
    await getUsersAll();
    expect(httpMock.get).toHaveBeenCalledWith("/users/all");
    await getProjects();
    expect(httpMock.get).toHaveBeenCalledWith("/projects");
    await createProject({ name: "工程A" });
    expect(httpMock.post).toHaveBeenCalledWith("/projects", { name: "工程A" });
    await getBranchInstances(3, { silent: true });
    expect(httpMock.get).toHaveBeenCalledWith("/branches/3/instances", {
      silent: true
    });
    await startBranchProject(11);
    expect(httpMock.post).toHaveBeenCalledWith("/branch-projects/11/start");
    await stopBranchProject(11);
    expect(httpMock.post).toHaveBeenCalledWith("/branch-projects/11/stop");
  });
});

describe("api/slotBooking 契约", () => {
  it("模板与日历", async () => {
    await getSlotTemplates();
    expect(httpMock.get).toHaveBeenCalledWith("/slot-templates");
    await deleteSlotTemplate(2);
    expect(httpMock.delete).toHaveBeenCalledWith("/slot-templates/2");
    await getSlotCalendar("2026-10");
    expect(httpMock.get).toHaveBeenCalledWith("/slot-calendar", {
      params: { month: "2026-10" }
    });
  });

  it("抢占/释放/列表分页", async () => {
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
    await getMyBookings(2, 10);
    expect(httpMock.get).toHaveBeenCalledWith("/slot-bookings/mine", {
      params: { page: 2, page_size: 10 }
    });
    await getSlotBookings({ status: "reserved", page: 1 });
    expect(httpMock.get).toHaveBeenCalledWith("/slot-bookings", {
      params: { status: "reserved", page: 1 }
    });
  });
});
