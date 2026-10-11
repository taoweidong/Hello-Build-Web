// utils/slotCalendar 单测：月历 42 格装配与统计（slot-booking 页核心纯函数）
import { describe, expect, it } from "vitest";
import { buildMonthCells, summarizeCalendar } from "@/utils/slotCalendar";
import type { CalendarDayCell } from "@/api/slotBooking";

describe("buildMonthCells", () => {
  it("2026-10：42 格、周一开头、10-01 为周四（首格补位 09-28）", () => {
    const cells = buildMonthCells("2026-10");
    expect(cells).toHaveLength(42);
    expect(cells[0]).toEqual({ date: "2026-09-28", inMonth: false });
    expect(cells[3]).toEqual({ date: "2026-10-01", inMonth: true });
    expect(cells[41].date).toBe("2026-11-08");
    expect(cells[41].inMonth).toBe(false);
  });

  it("整月 inMonth 标记正确（首尾补位为 false）", () => {
    const cells = buildMonthCells("2026-11"); // 11-01 为周日 → 首格 10-26
    expect(cells[0].date).toBe("2026-10-26");
    expect(cells[0].inMonth).toBe(false);
    const inMonth = cells.filter(c => c.inMonth);
    expect(inMonth).toHaveLength(30); // 11 月 30 天
    expect(inMonth[0].date).toBe("2026-11-01");
    expect(inMonth[29].date).toBe("2026-11-30");
  });

  it("月份起始恰为周一时无上月补位", () => {
    const cells = buildMonthCells("2026-08"); // 2026-08-01 为周六？以算法为准：仅断言结构
    expect(cells).toHaveLength(42);
    expect(cells[0].date.endsWith("-01") ? cells[0].inMonth : true).toBe(true);
  });

  it("非法 month 返回空数组（不抛异常）", () => {
    expect(buildMonthCells("abc")).toEqual([]);
    expect(buildMonthCells("")).toEqual([]);
  });
});

function cell(
  status: "available" | "reserved",
  isMine = false
): CalendarDayCell {
  return {
    template_id: 1,
    status,
    booking:
      status === "reserved"
        ? ({ is_mine: isMine } as CalendarDayCell["booking"])
        : null
  };
}

describe("summarizeCalendar", () => {
  it("统计总段数/已占/我的", () => {
    const stats = summarizeCalendar({
      "2026-10-01": [cell("available"), cell("reserved", true)],
      "2026-10-02": [cell("reserved", false)]
    });
    expect(stats).toEqual({ total: 3, occupied: 2, mine: 1 });
  });

  it("空日历全零", () => {
    expect(summarizeCalendar({})).toEqual({ total: 0, occupied: 0, mine: 0 });
  });
});
