// useBranchColors 单测：锁定「稳定取色 + 未知分支回退 + 色板循环」
import { describe, expect, it } from "vitest";
import { ref } from "vue";
import { BRANCH_PALETTE, useBranchColors } from "@/composables/useBranchColors";

describe("useBranchColors 分支配色", () => {
  it("色板为 6 色且首位为保留蓝", () => {
    expect(BRANCH_PALETTE).toHaveLength(6);
    expect(BRANCH_PALETTE[0]).toBe("#3b82f6");
  });

  it("分支从色板第二位开始取色（首位留给 UI 主色）", () => {
    const branches = ref([{ branch_id: 1 }]);
    const { branchColor } = useBranchColors(branches);
    expect(branchColor(1)).toBe(BRANCH_PALETTE[1]);
  });

  it("分支数超过色板时循环取色", () => {
    const branches = ref([
      { branch_id: 1 },
      { branch_id: 2 },
      { branch_id: 3 },
      { branch_id: 4 },
      { branch_id: 5 },
      { branch_id: 6 },
      { branch_id: 7 }
    ]);
    const { branchColor } = useBranchColors(branches);
    // 第 7 个分支回到色板第 2 位（(6+1) % 6 = 1）
    expect(branchColor(7)).toBe(BRANCH_PALETTE[1]);
  });

  it("同一分支取色稳定（多次调用结果一致）", () => {
    const branches = ref([{ branch_id: 1 }, { branch_id: 2 }]);
    const { branchColor } = useBranchColors(branches);
    const first = branchColor(2);
    expect(branchColor(2)).toBe(first);
  });

  it("未知分支回退色板首位", () => {
    const branches = ref([{ branch_id: 1 }]);
    const { branchColor } = useBranchColors(branches);
    expect(branchColor(999)).toBe(BRANCH_PALETTE[0]);
  });

  it("响应式：分支列表变化后映射随之更新", () => {
    const branches = ref([{ branch_id: 1 }]);
    const { branchColor } = useBranchColors(branches);
    expect(branchColor(2)).toBe(BRANCH_PALETTE[0]); // 尚不存在 → 回退
    branches.value = [{ branch_id: 1 }, { branch_id: 2 }];
    expect(branchColor(2)).toBe(BRANCH_PALETTE[2]); // 出现后取第 3 色
  });
});
