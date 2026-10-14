// 布局页装配助手：一行完成「查询 → 中枢 → 动作总线 → provide」
// 5 个布局页面各自调用一次，保证数据与动作口径完全一致。
//
// 返回结构刻意「扁平铺开」：中枢内的 ref 提升为顶层绑定，模板中可自动解包
// （Vue 只自动解包顶层 setup 绑定，`data.kpi` 这类嵌套访问不会解包）。
//
// 查询变更器（R4-F9/F-M7）：onVersionChange/onBranchChange/onScopeChange 等
// 处理器曾在五份布局文件逐字复制、goThisWeek 的周一计算在 s1/s4 各内联一份，
// 统一收敛到本文件（周一计算走 utils/week.mondayOf 唯一来源）。
import { ref } from "vue";
import dayjs from "dayjs";
import { mondayOf } from "@/utils/week";
import { useScheduleData, defaultWeekQuery } from "./useScheduleData";
import { useScheduleActions } from "./useScheduleActions";
import { providePanorama } from "./context";
import type { ScheduleQuery } from "./types";

export function usePanoramaPage(overrides: Partial<ScheduleQuery> = {}) {
  const query = ref<ScheduleQuery>(defaultWeekQuery(overrides));
  const data = useScheduleData(query);
  const actions = useScheduleActions(data);
  providePanorama({ data, actions });

  // ---- 查询变更器（五布局共用，禁止布局层再各自复制）----

  /** 切版本：分支 id 跨版本不同，必须同步重置分支筛选 */
  function setVersion(versionId: number | undefined) {
    query.value = { ...query.value, versionId, branchIds: [] };
  }

  function setBranches(branchIds: number[]) {
    query.value = { ...query.value, branchIds };
  }

  function setScope(scope: "all" | "mine") {
    query.value = { ...query.value, scope };
  }

  /** 直接改写日期范围（S3 月历翻月等自定义跨度场景） */
  function setDateRange(dateFrom: string, dateTo: string) {
    query.value = { ...query.value, dateFrom, dateTo };
  }

  /** 整体平移 N 天（保持跨度：S1/S4 翻周 ±7、S2/S5 翻日 ±1） */
  function shiftBy(days: number) {
    setDateRange(
      dayjs(query.value.dateFrom).add(days, "day").format("YYYY-MM-DD"),
      dayjs(query.value.dateTo).add(days, "day").format("YYYY-MM-DD")
    );
  }

  /** 收敛到今天单日（S2/S5「今天」按钮） */
  function goToday() {
    const today = dayjs().format("YYYY-MM-DD");
    setDateRange(today, today);
  }

  /** 回到本周周一~周日（S1/S4「本周」按钮） */
  function goThisWeek() {
    const monday = mondayOf(dayjs().format("YYYY-MM-DD"));
    setDateRange(monday, dayjs(monday).add(6, "day").format("YYYY-MM-DD"));
  }

  return {
    query,
    ...data,
    actions,
    setVersion,
    setBranches,
    setScope,
    setDateRange,
    shiftBy,
    goToday,
    goThisWeek
  };
}
