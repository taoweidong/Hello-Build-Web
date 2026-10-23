// utils/week 单测：周一计算、闭区间日期轴与中文星期数组（调度全景各布局共用纯函数）
import { describe, expect, it } from "vitest";
import dayjs from "dayjs";
import {
  buildDateRange,
  mondayOf,
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

describe("mondayOf 所在周周一（R4-F6/F9 唯一来源）", () => {
  it("周一自身返回自身", () => {
    expect(mondayOf("2026-10-12")).toBe("2026-10-12");
  });

  it("周中/周日回退到本周周一（day()=0 的周日不换到下一周）", () => {
    expect(mondayOf("2026-10-13")).toBe("2026-10-12"); // 周二
    expect(mondayOf("2026-10-15")).toBe("2026-10-12"); // 周四
    expect(mondayOf("2026-10-18")).toBe("2026-10-12"); // 周日
  });

  it("跨月回退（2026-10-01 所在周周一为 09-28）", () => {
    expect(mondayOf("2026-10-01")).toBe("2026-09-28");
  });

  it("与数据中枢 weekMondayOf 口径一致（weekly week_start 锚点）", () => {
    // 中枢以 dateFrom 所在周周一请求 /weekly：月历首屏 10-01 → 09-28（s3 spec 同口径）
    expect(mondayOf("2026-09-28")).toBe("2026-09-28");
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
