// 时段月历装配纯函数（S3 月历视图的 42 格装配，便于单测锁定）
import dayjs from "dayjs";

export interface MonthCell {
  date: string;
  inMonth: boolean;
}

/** 月历 42 格（周一开头，含上下月补位）；month 非法（"YYYY-MM" 之外）返回空数组 */
export function buildMonthCells(month: string): MonthCell[] {
  // 显式格式校验：dayjs 对 "abc-01" 之类输入会宽松解析，不能只靠 isValid
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) return [];
  const first = dayjs(`${month}-01`);
  if (!first.isValid()) return [];
  const offset = (first.day() + 6) % 7; // day(): 0=周日 → 转周一开头
  const start = first.subtract(offset, "day");
  const list: MonthCell[] = [];
  for (let i = 0; i < 42; i++) {
    const d = start.add(i, "day");
    list.push({
      date: d.format("YYYY-MM-DD"),
      inMonth: d.format("YYYY-MM") === month
    });
  }
  return list;
}
