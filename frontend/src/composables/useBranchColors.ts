/**
 * 分支配色：固定色板 + 按 branch_id 稳定取色。
 *
 * 唯一消费者为调度全景数据中枢（useScheduleData）——此前三处页面各自复制
 * （2026-10-11 质量复评 M-7），改配色需同步多处；weekly/weekly-new 页已随
 * 2026-10-20 页面精简删除，禁止在页面层再复制本逻辑。
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
 * @returns branchColor 取色函数（未知分支回退色板首位）；映射为内部实现
 * 不再导出（R7-F11：生产仅消费 branchColor，映射本身无外部消费者）
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

  return { branchColor };
}
