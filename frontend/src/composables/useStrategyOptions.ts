/**
 * 报告页版本/策略级联选项（report/index 与 report/detail 共用）。
 *
 * 此前两页各自复制版本去重 + 策略按版本过滤逻辑（2026-10-11 复评 L-7），
 * 报告存文本快照、过滤按名称，与后端 FilterSet 对齐。
 */
import { computed, ref, type Ref } from "vue";
import { getStrategies } from "@/api/strategy";
import type { StrategyItem } from "@/api/types";

export function useStrategyOptions(
  selectedVersionName: Ref<string | undefined | null>
) {
  const allStrategies = ref<StrategyItem[]>([]);

  /** 加载全量策略（供去重与级联）；失败置空不影响主流程 */
  async function loadStrategyOptions(): Promise<void> {
    try {
      allStrategies.value = await getStrategies();
    } catch {
      allStrategies.value = [];
    }
  }

  const versionOptions = computed(() => {
    const names = new Set<string>();
    allStrategies.value.forEach(s => {
      if (s.version_name) names.add(s.version_name);
    });
    return Array.from(names, name => ({ name }));
  });

  const strategyOptions = computed(() =>
    allStrategies.value.filter(
      s => s.version_name === selectedVersionName.value
    )
  );

  return {
    allStrategies,
    versionOptions,
    strategyOptions,
    loadStrategyOptions
  };
}
