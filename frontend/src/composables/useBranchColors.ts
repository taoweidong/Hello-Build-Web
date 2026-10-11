/**
 * 分支配色：固定色板 + 按 branch_id 稳定取色。
 *
 * 供周视图（weekly）与日视图（weekly-new）共用 —— 此前两页各自复制一份
 * （2026-10-11 质量复评 M-7），改配色需同步两处，遗漏会导致同一分支
 * 在两个页面显示不同颜色。
 */
import { computed, type Ref } from "vue";

/** 固定 6 色板：首位蓝色保留给 UI 主色，分支从第二位开始取 */
export const BRANCH_PALETTE = [
  "#3b82f6",
  "#8b5cf6",
  "#f59e0b",
  "#10b981",
  "#ef4444",
  "#06b6d4"
] as const;

/**
 * 按分支列表构建 branch_id → 颜色 的稳定映射。
 *
 * @param branches 响应式分支列表（至少含 branch_id 字段）
 * @returns branchColorMap 一次计算的映射；branchColor 取色函数（未知分支回退色板首位）
 */
export function useBranchColors(branches: Ref<Array<{ branch_id: number }>>) {
  // 分支配色映射：一次计算，避免模板内重复 O(n) 查找
  const branchColorMap = computed(() => {
    const map = new Map<number, string>();
    branches.value.forEach((b, idx) => {
      map.set(b.branch_id, BRANCH_PALETTE[(idx + 1) % BRANCH_PALETTE.length]);
    });
    return map;
  });

  function branchColor(branchId: number): string {
    return branchColorMap.value.get(branchId) ?? BRANCH_PALETTE[0];
  }

  return { branchColorMap, branchColor };
}
