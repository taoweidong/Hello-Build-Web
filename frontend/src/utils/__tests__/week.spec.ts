// utils/week 单测：ISO 周序号、本月周列表与中文星期数组（weekly-new 页核心纯函数）
import { describe, expect, it } from "vitest";
import dayjs from "dayjs";
import {
  buildDateRange,
  buildMonthWeeks,
  isoWeek,
  WEEKDAY_CN_MON,
  WEEKDAY_CN_SUN
} from "@/utils/week";

describe("WEEKDAY_CN_MON / WEEKDAY_CN_SUN 中文星期数组", () => {
  it("周一开头：长度 7、首周一末周日（isoweekday 1-7 口径，下标 0 = 周一）", () => {
    expect(WEEKDAY_CN_MON).toHaveLength(7);
    expect(WEEKDAY_CN_MON[0]).toBe("周一");
    expect(WEEKDAY_CN_MON[6]).toBe("周日");
  });

  it("周日开头：长度 7、首周日末周六（配合 dayjs().day() 0-6 下标取值）", () => {
    expect(WEEKDAY_CN_SUN).toHaveLength(7);
    expect(WEEKDAY_CN_SUN[0]).toBe("周日");
    expect(WEEKDAY_CN_SUN[6]).toBe("周六");
  });

  it("两数组星期名集合一致，且与 dayjs 下标对齐", () => {
    expect([...WEEKDAY_CN_MON].sort()).toEqual([...WEEKDAY_CN_SUN].sort());
    // dayjs("2026-10-12") 为周一：day()=1 → 周日开头数组下标 1 = 周一
    expect(WEEKDAY_CN_SUN[dayjs("2026-10-12").day()]).toBe("周一");
    // isoweekday 1 → 周一开头数组下标 0 = 周一
    expect(WEEKDAY_CN_MON[1 - 1]).toBe("周一");
  });
});

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

describe("buildDateRange", () => {
  it("闭区间：from 与 to 都包含在内", () => {
    expect(buildDateRange("2026-10-12", "2026-10-14")).toEqual([
      "2026-10-12",
      "2026-10-13",
      "2026-10-14"
    ]);
  });

  it("单日区间返回一日", () => {
    expect(buildDateRange("2026-10-13", "2026-10-13")).toEqual(["2026-10-13"]);
  });

  it("跨月跨年连续无跳日（覆盖月份长度不等）", () => {
    const range = buildDateRange("2026-12-30", "2027-01-02");
    expect(range).toEqual([
      "2026-12-30",
      "2026-12-31",
      "2027-01-01",
      "2027-01-02"
    ]);
  });

  it("to 早于 from 返回空数组", () => {
    expect(buildDateRange("2026-10-14", "2026-10-12")).toEqual([]);
  });

  it("非法日期返回空数组", () => {
    expect(buildDateRange("not-a-date", "2026-10-12")).toEqual([]);
    expect(buildDateRange("2026-10-12", "")).toEqual([]);
  });
});
