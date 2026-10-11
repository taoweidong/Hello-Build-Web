// 周/日历纯函数（自 weekly-new 页抽取，算法与原实现一致，便于单测锁定）
import dayjs, { type Dayjs } from "dayjs";

/** ISO-8601 周序号（1-53）。

以本地日历日计算（所在周的周四落在哪一年即该年第几周）。
原实现用 getUTC* 系列，在东八区会把本地零点换算到前一天 16:00 UTC，
导致周一被算进上一周、同一周内序号跳变（2026-10-12 质量优化第二轮修复）。 */
export function isoWeek(dateStr: string): number {
  const d = dayjs(dateStr).startOf("day");
  const n = d.day() || 7; // 1..7，周一=1、周日=7
  const thursday = d.add(4 - n, "day");
  const yearStart = thursday.startOf("year");
  return Math.ceil((thursday.diff(yearStart, "day") + 1) / 7);
}

/** 本月周列表：本月第一个周一为第 1 周；now 可注入便于测试 */
export function buildMonthWeeks(
  now: Dayjs = dayjs()
): Array<{ value: string; label: string }> {
  const startOfMonth = now.startOf("month");
  const first =
    startOfMonth.day() === 0 ? startOfMonth.add(1, "day") : startOfMonth.day(1);
  const firstMonday =
    first.month() === startOfMonth.month() ? first : first.add(7, "day");
  const result: Array<{ value: string; label: string }> = [];
  for (let i = 0; i < 6; i++) {
    const monday = firstMonday.add(i * 7, "day");
    if (monday.month() !== startOfMonth.month()) break;
    result.push({
      value: monday.format("YYYY-MM-DD"),
      label: `第${i + 1}周（${monday.format("MM.DD")} - ${monday.add(6, "day").format("MM.DD")}）`
    });
  }
  return result;
}
