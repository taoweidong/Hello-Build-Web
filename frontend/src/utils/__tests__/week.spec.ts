// utils/week 单测：ISO 周序号与本月周列表（weekly-new 页核心纯函数）
import { describe, expect, it } from "vitest";
import dayjs from "dayjs";
import { buildMonthWeeks, isoWeek } from "@/utils/week";

describe("isoWeek", () => {
  it("2021-01-01（周五）属于 2020 年第 53 周", () => {
    expect(isoWeek("2021-01-01")).toBe(53);
  });

  it("同一周内的日期序号一致，跨周不同", () => {
    // 2026-10-12 为周一，10-18 为周日（同一 ISO 周）；10-11 属上一周
    expect(isoWeek("2026-10-12")).toBe(isoWeek("2026-10-18"));
    expect(isoWeek("2026-10-11")).not.toBe(isoWeek("2026-10-12"));
  });

  it("2024-01-01（周一）为第 1 周", () => {
    expect(isoWeek("2024-01-01")).toBe(1);
  });
});

describe("buildMonthWeeks", () => {
  it("2026-10：第一个周一 10-05 为第 1 周，共 4 周", () => {
    const weeks = buildMonthWeeks(dayjs("2026-10-15"));
    expect(weeks).toHaveLength(4);
    expect(weeks[0].value).toBe("2026-10-05");
    expect(weeks[0].label).toBe("第1周（10.05 - 10.11）");
    expect(weeks[3].value).toBe("2026-10-26");
  });

  it("2026-11：11-02 为第 1 周，共 5 周", () => {
    const weeks = buildMonthWeeks(dayjs("2026-11-15"));
    expect(weeks).toHaveLength(5);
    expect(weeks[0].value).toBe("2026-11-02");
    expect(weeks[4].value).toBe("2026-11-30");
  });

  it("月初即周一时该周为第 1 周（2026-08-03 为周一）", () => {
    const weeks = buildMonthWeeks(dayjs("2026-08-10"));
    expect(weeks[0].value).toBe("2026-08-03");
  });

  it("value 均为 YYYY-MM-DD 且间隔 7 天", () => {
    const weeks = buildMonthWeeks(dayjs("2026-10-15"));
    weeks.forEach((w, i) => {
      expect(w.value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      if (i > 0) {
        const prev = dayjs(weeks[i - 1].value);
        expect(dayjs(w.value).diff(prev, "day")).toBe(7);
      }
    });
  });
});
