// utils/business.ts 单测：业务用户读取与时间解析
import { beforeEach, describe, expect, it } from "vitest";
import {
  canApproveBorrowFlow,
  canEditPanorama,
  formatTime,
  getCurrentUser,
  isPastSlot,
  parseTime,
  timeToMs
} from "@/utils/business";

describe("utils/business", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  describe("getCurrentUser", () => {
    it("读取业务用户信息", () => {
      localStorage.setItem(
        "build-user-info",
        JSON.stringify({ id: 1, username: "pm1", role: "pm" })
      );
      const user = getCurrentUser();
      expect(user?.username).toBe("pm1");
      expect(user?.role).toBe("pm");
    });

    it("无数据返回 null", () => {
      expect(getCurrentUser()).toBeNull();
    });

    it("损坏的 JSON 返回 null 而非抛异常", () => {
      localStorage.setItem("build-user-info", "{broken");
      expect(getCurrentUser()).toBeNull();
    });
  });

  describe("parseTime / timeToMs / formatTime", () => {
    it("解析后端 '%Y-%m-%dT%H:%M:%S' 格式", () => {
      const d = parseTime("2026-08-10T22:00:00");
      expect(d.getFullYear()).toBe(2026);
      expect(d.getMonth()).toBe(7);
      expect(d.getDate()).toBe(10);
      expect(d.getHours()).toBe(22);
    });

    it("解析空格分隔格式", () => {
      const d = parseTime("2026-08-10 22:00:00");
      expect(d.getHours()).toBe(22);
    });

    it("timeToMs 与 Date.getTime 一致", () => {
      expect(timeToMs("2026-08-10T22:00:00")).toBe(
        parseTime("2026-08-10T22:00:00").getTime()
      );
    });

    it("formatTime 输出 MM-DD HH:mm", () => {
      expect(formatTime("2026-08-10T22:05:00")).toBe("08-10 22:05");
    });
  });

  describe("canEditPanorama 全景编辑权限", () => {
    it("admin 可编辑任意版本", () => {
      expect(canEditPanorama("admin", undefined, 1)).toBe(true);
      expect(canEditPanorama("admin", undefined, 2)).toBe(true);
    });

    it("pm 仅可编辑绑定版本", () => {
      expect(canEditPanorama("pm", 1, 1)).toBe(true);
      expect(canEditPanorama("pm", 1, 2)).toBe(false);
      expect(canEditPanorama("pm", undefined, 1)).toBe(false);
    });

    it("其他角色（外部查看人员）只读", () => {
      expect(canEditPanorama("builder", undefined, 1)).toBe(false);
      expect(canEditPanorama("tester", undefined, 1)).toBe(false);
      expect(canEditPanorama("integrator", undefined, 1)).toBe(false);
    });

    it("角色缺失或版本未选时不允许编辑", () => {
      expect(canEditPanorama(undefined, 1, 1)).toBe(false);
      expect(canEditPanorama("admin", undefined, undefined)).toBe(false);
    });
  });

  describe("isPastSlot 过期时段判定", () => {
    const now = new Date("2026-10-11T15:00:00");
    it("日期+时刻早于当前时间判为已过期", () => {
      expect(isPastSlot("2026-10-11", "09:30", now)).toBe(true);
      expect(isPastSlot("2026-10-10", "23:00", now)).toBe(true);
    });
    it("晚于当前时间判为未过期", () => {
      expect(isPastSlot("2026-10-11", "21:00", now)).toBe(false);
      expect(isPastSlot("2026-10-12", "02:00", now)).toBe(false);
    });
    it("恰好等于当前时刻不算过期（未早于）", () => {
      expect(isPastSlot("2026-10-11", "15:00", now)).toBe(false);
    });
    it("无法解析的时间按未过期处理", () => {
      expect(isPastSlot("bad-date", "25:99", now)).toBe(false);
    });
  });
});

describe("canApproveBorrowFlow", () => {
  const flow = { source_version_id: 7 };

  it("admin 可审批任意电子流", () => {
    expect(canApproveBorrowFlow({ role: "admin" }, flow)).toBe(true);
  });

  it("pm 仅可审批来源版本为自己的电子流", () => {
    expect(
      canApproveBorrowFlow({ role: "pm", bound_version_id: 7 }, flow)
    ).toBe(true);
    expect(
      canApproveBorrowFlow({ role: "pm", bound_version_id: 8 }, flow)
    ).toBe(false);
    expect(canApproveBorrowFlow({ role: "pm" }, flow)).toBe(false);
  });

  it("其余角色与未登录不可审批", () => {
    expect(canApproveBorrowFlow({ role: "builder" }, flow)).toBe(false);
    expect(canApproveBorrowFlow({ role: "tester" }, flow)).toBe(false);
    expect(canApproveBorrowFlow(null, flow)).toBe(false);
  });
});
