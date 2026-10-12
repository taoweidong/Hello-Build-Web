// 布局页装配助手：一行完成「查询 → 中枢 → 动作总线 → provide」
// 5 个布局页面各自调用一次，保证数据与动作口径完全一致。
//
// 返回结构刻意「扁平铺开」：中枢内的 ref 提升为顶层绑定，模板中可自动解包
// （Vue 只自动解包顶层 setup 绑定，`data.kpi` 这类嵌套访问不会解包）。
import { ref } from "vue";
import { useScheduleData, defaultWeekQuery } from "./useScheduleData";
import { useScheduleActions } from "./useScheduleActions";
import { providePanorama } from "./context";
import type { ScheduleQuery } from "./types";

export function usePanoramaPage(overrides: Partial<ScheduleQuery> = {}) {
  const query = ref<ScheduleQuery>(defaultWeekQuery(overrides));
  const data = useScheduleData(query);
  const actions = useScheduleActions(data);
  providePanorama({ data, actions });
  return { query, ...data, actions };
}
