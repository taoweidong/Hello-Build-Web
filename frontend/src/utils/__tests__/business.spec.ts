// utils/business.ts 单测：业务用户读取与时间解析
import { beforeEach, describe, expect, it } from "vitest";
import {
  formatTime,
  getCurrentUser,
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
});
