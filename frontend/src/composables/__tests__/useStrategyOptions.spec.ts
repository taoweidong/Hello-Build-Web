// useStrategyOptions 单测：版本去重 + 按名级联过滤 + 失败置空（report 两页共用）
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import type { StrategyItem } from "@/api/types";

const getStrategies = vi.hoisted(() => vi.fn());
vi.mock("@/api/strategy", () => ({ getStrategies }));

import { useStrategyOptions } from "@/composables/useStrategyOptions";

function strategy(version_name: string, name: string): StrategyItem {
  // 仅构造被测逻辑关心的字段（版本名 + 策略名）
  return { version_name, name } as unknown as StrategyItem;
}

describe("useStrategyOptions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("版本选项去重、空版本名不入选；策略选项按所选版本名级联过滤", async () => {
    getStrategies.mockResolvedValue([
      strategy("27A", "27A-master-晚间"),
      strategy("27A", "27A-TR5-晚间"),
      strategy("27B", "27B-master-晚间"),
      strategy("", "无版本策略")
    ]);
    const selected = ref<string | undefined | null>(null);
    const { versionOptions, strategyOptions, loadStrategyOptions } =
      useStrategyOptions(selected);

    await loadStrategyOptions();
    expect(getStrategies).toHaveBeenCalledTimes(1);
    expect(versionOptions.value).toEqual([{ name: "27A" }, { name: "27B" }]);

    // 未选版本时无策略候选
    expect(strategyOptions.value).toEqual([]);
    selected.value = "27A";
    expect(strategyOptions.value.map(s => s.name)).toEqual([
      "27A-master-晚间",
      "27A-TR5-晚间"
    ]);
    selected.value = "27B";
    expect(strategyOptions.value).toHaveLength(1);
  });

  it("加载失败置空、不抛出（不影响报告页主流程）", async () => {
    getStrategies.mockRejectedValue(new Error("network"));
    const selected = ref<string | undefined | null>(null);
    const { allStrategies, versionOptions, loadStrategyOptions } =
      useStrategyOptions(selected);
    await expect(loadStrategyOptions()).resolves.toBeUndefined();
    expect(allStrategies.value).toEqual([]);
    expect(versionOptions.value).toEqual([]);
  });
});
