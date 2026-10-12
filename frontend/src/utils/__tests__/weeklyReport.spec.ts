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

  it("today 不在展示周：待执行/已完成仍相对传入的 today 判定", () => {
    // today 远早于 now（如查看历史周时传入的当天已整周过去）→ 全部已完成
    const past = computeKpis(strategies, 3, "2020-01-01", now);
    expect(past.todayDone).toBe(3);
    expect(past.todayPending).toBe(0);
    // today 远晚于 now → 全部待执行
    const future = computeKpis(strategies, 3, "2030-01-01", now);
    expect(future.todayDone).toBe(0);
    expect(future.todayPending).toBe(3);
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

  it("非法时间守卫：越界/非数字/空串条目跳过，不 TypeError 也不误计入 0 点", () => {
    const dirty = [
      s({
        strategy_id: 20,
        strategy_name: "越界",
        branch_id: 1,
        build_start_time: "25:00", // 小时越界：跳过（旧实现 buckets[25] 直接 TypeError）
        push_start_time: "26:30"
      }),
      s({
        strategy_id: 21,
        strategy_name: "非数字",
        branch_id: 1,
        build_start_time: "ab:cd", // 非数字：跳过（旧实现误计入 0 点）
        push_start_time: "xx:00"
      }),
      s({
        strategy_id: 22,
        strategy_name: "空串",
        branch_id: 1,
        build_start_time: "", // 空串：跳过
        push_start_time: null
      }),
      s({
        strategy_id: 23,
        strategy_name: "正常",
        branch_id: 1,
        build_start_time: "07:00"
      })
    ];
    const buckets = computeHourTrend(dirty);
    expect(buckets).toHaveLength(24);
    // 仅合法条目计入
    expect(buckets[7]).toMatchObject({ build: 1, push: 0, total: 1 });
    expect(buckets[0].total).toBe(0);
    expect(buckets.reduce((sum, b) => sum + b.total, 0)).toBe(1);
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

  it("字号封顶 22px：次数 5 及以上不再增长", () => {
    const many = Array.from({ length: 8 }, (_, i) =>
      s({
        strategy_id: 100 + i,
        strategy_name: `策略${i}`,
        branch_id: 1,
        build_start_time: "08:00",
        template_name: "高频模板"
      })
    );
    const tags = computeTagCloud(many);
    const hot = tags.find(t => t.text === "高频模板");
    // 模板出现 8 次：12 + (8-1)*2.5 = 29.5 → 封顶 22
    expect(hot?.count).toBe(8);
    expect(hot?.size).toBe(22);
    // 恰好 5 次到达封顶：12 + 4*2.5 = 22
    const five = Array.from({ length: 5 }, (_, i) =>
      s({
        strategy_id: 200 + i,
        strategy_name: `策略${i}`,
        branch_id: 1,
        build_start_time: "08:00",
        template_name: "五连模板"
      })
    );
    expect(computeTagCloud(five).find(t => t.text === "五连模板")?.size).toBe(
      22
    );
  });

  it("三键排序：次数相同 → 类型（策略<模板<分支）→ 名称升序", () => {
    // 名称用 ASCII 前缀，规避中文 collation 的环境差异
    const rows = [
      s({
        strategy_id: 31,
        strategy_name: "S-b",
        branch_id: 1,
        build_start_time: "08:00",
        template_name: "T-b"
      }),
      s({
        strategy_id: 32,
        strategy_name: "S-a",
        branch_id: 2,
        build_start_time: "09:00",
        template_name: "T-a"
      })
    ];
    const tags = computeTagCloud(rows);
    // 全部条目次数=1：先按类型（strategy → template → branch），同类型按名称 localeCompare 升序
    expect(tags.map(t => t.text)).toEqual([
      "S-a",
      "S-b",
      "T-a",
      "T-b",
      "分支1",
      "分支2"
    ]);
  });
});
