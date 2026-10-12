import { describe, expect, it } from "vitest";
import type { WeeklyStrategy } from "@/api/types";
import {
  collectTimePoints,
  computeBranchLoad,
  computeHourTrend,
  computeKpis,
  computeTagCloud
} from "../weeklyReport";

/** 构造策略条目（仅默认值差异字段） */
function s(
  partial: Partial<WeeklyStrategy> &
    Pick<
      WeeklyStrategy,
      "strategy_id" | "strategy_name" | "branch_id" | "build_start_time"
    >
): WeeklyStrategy {
  return {
    branch_name: `分支${partial.branch_id}`,
    push_start_time: null,
    push_mode: "normal",
    template_name: "标准模板",
    ...partial
  } as WeeklyStrategy;
}

const strategies: WeeklyStrategy[] = [
  s({
    strategy_id: 1,
    strategy_name: "早间回归",
    branch_id: 1,
    build_start_time: "06:30",
    push_start_time: "09:00",
    push_mode: "sync",
    template_name: "冒烟A"
  }),
  s({
    strategy_id: 2,
    strategy_name: "午间构建",
    branch_id: 1,
    build_start_time: "12:30",
    template_name: "冒烟A"
  }),
  s({
    strategy_id: 3,
    strategy_name: "晚间发布",
    branch_id: 2,
    build_start_time: "22:00",
    push_start_time: "23:30"
  })
];

const branches = [
  { branch_id: 1, branch_name: "27A-master" },
  { branch_id: 2, branch_name: "27A-TR6" },
  { branch_id: 3, branch_name: "27A-dev" }
];

describe("collectTimePoints", () => {
  it("构建+推送去重升序", () => {
    expect(collectTimePoints(strategies)).toEqual([
      "06:30",
      "09:00",
      "12:30",
      "22:00",
      "23:30"
    ]);
  });

  it("空列表返回空数组", () => {
    expect(collectTimePoints([])).toEqual([]);
  });
});

describe("computeKpis", () => {
  // 固定「现在」：周三 15:00（today 传周三）
  const now = new Date("2026-10-14T15:00:00");

  it("聚合任务/推送/分支/时间点", () => {
    const k = computeKpis(strategies, 3, "2026-10-14", now);
    expect(k.tasks).toBe(3);
    expect(k.buildTasks).toBe(3);
    expect(k.pushTasks).toBe(2);
    expect(k.syncPush).toBe(1);
    expect(k.normalPush).toBe(1);
    expect(k.branchCount).toBe(2); // 仅统计有任务的分支
    expect(k.branchTotal).toBe(3);
    expect(k.timePoints).toBe(5);
    expect(k.earliestBuild).toBe("06:30");
    expect(k.latestBuild).toBe("22:00");
  });

  it("今日待执行/已完成按时刻切分", () => {
    const k = computeKpis(strategies, 3, "2026-10-14", now);
    // 06:30 / 12:30 已过；22:00 未过
    expect(k.todayDone).toBe(2);
    expect(k.todayPending).toBe(1);
  });

  it("空数据回退 --:--", () => {
    const k = computeKpis([], 0, "2026-10-14", now);
    expect(k.earliestBuild).toBe("--:--");
    expect(k.latestBuild).toBe("--:--");
    expect(k.todayPending).toBe(0);
  });
});

describe("computeBranchLoad", () => {
  it("按总量降序、含构建/推送拆分与注入配色", () => {
    const rows = computeBranchLoad(strategies, branches, id => `#c${id}`);
    expect(rows.map(r => r.branch_id)).toEqual([1, 2]); // 无任务的分支 3 被过滤
    expect(rows[0]).toMatchObject({
      branch_name: "27A-master",
      color: "#c1",
      total: 2,
      build: 2,
      push: 1
    });
    expect(rows[1]).toMatchObject({ total: 1, build: 1, push: 1 });
  });

  it("空输入返回空数组", () => {
    expect(computeBranchLoad([], branches, () => "#000")).toEqual([]);
  });
});

describe("computeHourTrend", () => {
  it("按小时聚合构建/推送", () => {
    const buckets = computeHourTrend(strategies);
    expect(buckets).toHaveLength(24);
    expect(buckets[6]).toMatchObject({ build: 1, push: 0, total: 1 });
    expect(buckets[9]).toMatchObject({ build: 0, push: 1, total: 1 });
    expect(buckets[12]).toMatchObject({ build: 1, push: 0, total: 1 });
    expect(buckets[22]).toMatchObject({ build: 1, push: 0, total: 1 });
    expect(buckets[23]).toMatchObject({ build: 0, push: 1, total: 1 });
    expect(buckets[0].total).toBe(0);
  });

  it("构建与推送同小时则叠加", () => {
    const same = [
      s({
        strategy_id: 9,
        strategy_name: "x",
        branch_id: 1,
        build_start_time: "08:00",
        push_start_time: "08:30"
      })
    ];
    expect(computeHourTrend(same)[8]).toMatchObject({
      build: 1,
      push: 1,
      total: 2
    });
  });
});

describe("computeTagCloud", () => {
  it("按次数降序并限制条数", () => {
    const tags = computeTagCloud(strategies, 10);
    // 模板「冒烟A」2 次居首；字号随次数增长
    expect(tags[0]).toMatchObject({
      text: "冒烟A",
      kind: "template",
      count: 2
    });
    expect(tags[0].size).toBeGreaterThan(12);
    expect(tags.length).toBeLessThanOrEqual(10);
    // 策略名各 1 次
    const strategyTags = tags.filter(t => t.kind === "strategy");
    expect(strategyTags).toHaveLength(3);
    expect(strategyTags.every(t => t.count === 1 && t.size === 12)).toBe(true);
  });

  it("空输入返回空数组", () => {
    expect(computeTagCloud([])).toEqual([]);
  });
});
