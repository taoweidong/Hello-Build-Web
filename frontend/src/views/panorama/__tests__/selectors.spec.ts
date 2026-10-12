// selectors 纯投影单测：5 个布局共用的排序/分组/冲突/指标/分列/热力
import { describe, expect, it } from "vitest";
import {
  buildAgenda,
  buildHeatmap,
  buildKpi,
  collectTimePoints,
  detectCrossSourceConflicts,
  durationOf,
  groupByBranch,
  groupByDay,
  lanePack,
  sortEvents
} from "@/views/panorama/selectors";
import { makeEvent } from "./fixtures";
import type { ScheduleEvent } from "@/views/panorama/types";

/** 构造 reserved 时段事件（status=reserved 才参与冲突判定） */
function slotEvent(over: Partial<ScheduleEvent> = {}): ScheduleEvent {
  return makeEvent({
    id: "slot:2026-10-13:1",
    source: "slot",
    kind: "slot",
    time: "09:00",
    endTime: "10:00",
    durationMin: 60,
    status: "reserved",
    statusText: "已抢占",
    ...over
  });
}

describe("sortEvents", () => {
  it("按日期升序、同日按起始时刻升序、同时刻按时长降序", () => {
    const list = [
      makeEvent({ id: "b", date: "2026-10-14", time: "08:00" }),
      makeEvent({ id: "a", date: "2026-10-13", time: "12:00" }),
      makeEvent({
        id: "c",
        date: "2026-10-13",
        time: "08:00",
        durationMin: 10
      }),
      makeEvent({ id: "d", date: "2026-10-13", time: "08:00", durationMin: 90 })
    ];
    expect(sortEvents(list).map(e => e.id)).toEqual(["d", "c", "a", "b"]);
  });

  it("纯函数：不改动入参数组", () => {
    const list = [
      makeEvent({ id: "x", time: "12:00" }),
      makeEvent({ id: "y", time: "08:00" })
    ];
    const snapshot = list.map(e => e.id);
    sortEvents(list);
    expect(list.map(e => e.id)).toEqual(snapshot);
  });
});

describe("groupByDay", () => {
  it("仅返回有事件的日期，组内保持排序后顺序", () => {
    const grouped = groupByDay([
      makeEvent({ id: "a", date: "2026-10-14", time: "08:00" }),
      makeEvent({ id: "b", date: "2026-10-13", time: "09:00" }),
      makeEvent({ id: "c", date: "2026-10-13", time: "08:00" })
    ]);
    expect(Object.keys(grouped)).toEqual(["2026-10-13", "2026-10-14"]);
    expect(grouped["2026-10-13"].map(e => e.id)).toEqual(["c", "b"]);
  });
});

describe("buildAgenda", () => {
  it("投影字段完整且不含 raw / date 之外多余字段", () => {
    const agenda = buildAgenda([makeEvent()]);
    expect(agenda).toHaveLength(1);
    expect(agenda[0]).toEqual({
      id: "strategy:1#build",
      source: "strategy",
      kind: "build",
      date: "2026-10-13",
      time: "08:00",
      endTime: "08:30",
      durationMin: 30,
      title: "构建 · 主链路策略",
      subtitle: "main · 标准模板 · 正常流程",
      branchName: "main",
      versionName: "v3.2",
      color: "#3b82f6",
      statusText: "构建",
      past: false,
      mine: false,
      permissions: agenda[0].permissions
    });
  });

  it("顺序与 sortEvents 一致", () => {
    const list = [
      makeEvent({ id: "late", date: "2026-10-14", time: "08:00" }),
      makeEvent({ id: "early", date: "2026-10-13", time: "09:00" })
    ];
    expect(buildAgenda(list).map(i => i.id)).toEqual(["early", "late"]);
  });
});

describe("detectCrossSourceConflicts", () => {
  it("策略时间点落在已抢占时段内 → 命中", () => {
    const conflicts = detectCrossSourceConflicts([
      slotEvent(),
      makeEvent({
        id: "strategy:1#build",
        time: "09:20",
        endTime: "09:20",
        durationMin: 0
      })
    ]);
    expect(conflicts.map(e => e.id)).toEqual(["strategy:1#build"]);
  });

  it("策略时间点在时段之外 → 不命中", () => {
    expect(
      detectCrossSourceConflicts([
        slotEvent(),
        makeEvent({
          id: "strategy:1#build",
          time: "11:00",
          endTime: "11:00",
          durationMin: 0
        })
      ])
    ).toEqual([]);
  });

  it("时段为 available（未抢占）→ 不判定冲突", () => {
    expect(
      detectCrossSourceConflicts([
        slotEvent({ status: "available" }),
        makeEvent({ time: "09:30", endTime: "09:30", durationMin: 0 })
      ])
    ).toEqual([]);
  });

  it("跨日期不误判：策略与时段不在同一天", () => {
    expect(
      detectCrossSourceConflicts([
        slotEvent({ date: "2026-10-13" }),
        makeEvent({
          date: "2026-10-14",
          time: "09:30",
          endTime: "09:30",
          durationMin: 0
        })
      ])
    ).toEqual([]);
  });

  it("借用来源不参与冲突判定", () => {
    expect(
      detectCrossSourceConflicts([
        slotEvent(),
        makeEvent({ source: "borrow", kind: "borrow", time: "09:30" })
      ])
    ).toEqual([]);
  });
});

describe("buildKpi", () => {
  const events = [
    makeEvent({
      id: "s1",
      source: "strategy",
      kind: "build",
      date: "2026-10-13",
      time: "08:00"
    }),
    makeEvent({
      id: "s2",
      source: "strategy",
      kind: "smoke",
      date: "2026-10-13",
      time: "08:30"
    }),
    makeEvent({ id: "k1", source: "slot", status: "reserved", mine: true }),
    makeEvent({ id: "k2", source: "slot", status: "reserved", mine: false }),
    makeEvent({ id: "k3", source: "slot", status: "available", mine: false }),
    makeEvent({
      id: "b1",
      source: "borrow",
      kind: "borrow",
      date: "2026-10-13",
      time: "09:15"
    })
  ];

  it("各计数口径：今日构建 / 抢占 / 总时段 / 待审 / 我的", () => {
    const kpi = buildKpi(events, "2026-10-13");
    expect(kpi.todayBuild).toBe(1);
    expect(kpi.weekSlotOccupied).toBe(2);
    expect(kpi.weekSlotTotal).toBe(3);
    expect(kpi.pendingBorrow).toBe(1);
    expect(kpi.mySlots).toBe(1);
  });

  it("占用率四舍五入：2/3 → 67", () => {
    expect(buildKpi(events, "2026-10-13").occupancyRate).toBe(67);
  });

  it("无时段时占用率为 0（不除零）", () => {
    expect(buildKpi([makeEvent()], "2026-10-13").occupancyRate).toBe(0);
  });

  it("conflictCount 与 detectCrossSourceConflicts 同源", () => {
    const withConflict = [
      ...events,
      makeEvent({
        id: "s3",
        source: "strategy",
        time: "09:30",
        endTime: "09:30",
        durationMin: 0
      })
    ];
    expect(buildKpi(withConflict, "2026-10-13").conflictCount).toBe(1);
  });
});

describe("lanePack", () => {
  it("不重叠的事件共用同一子泳道", () => {
    const { lanes, laneCount } = lanePack([
      makeEvent({ id: "a", time: "08:00", endTime: "09:00" }),
      makeEvent({ id: "b", time: "09:00", endTime: "10:00" })
    ]);
    expect(lanes.get("a")).toBe(0);
    expect(lanes.get("b")).toBe(0);
    expect(laneCount).toBe(1);
  });

  it("重叠事件分列；边界相接不算重叠", () => {
    const { lanes, laneCount } = lanePack([
      makeEvent({ id: "a", time: "08:00", endTime: "09:00" }),
      makeEvent({ id: "b", time: "08:30", endTime: "09:30" }),
      makeEvent({ id: "c", time: "09:00", endTime: "10:00" })
    ]);
    expect(lanes.get("a")).toBe(0);
    expect(lanes.get("b")).toBe(1);
    // c 与 a 边界相接，可复用第 0 列
    expect(lanes.get("c")).toBe(0);
    expect(laneCount).toBe(2);
  });

  it("点事件（durationMin=0）按 1 分钟处理，不会互相重叠", () => {
    const { lanes, laneCount } = lanePack([
      makeEvent({ id: "a", time: "08:00", endTime: "08:00", durationMin: 0 }),
      makeEvent({ id: "b", time: "08:00", endTime: "08:00", durationMin: 0 })
    ]);
    expect(lanes.get("a")).toBe(0);
    expect(lanes.get("b")).toBe(1);
    expect(laneCount).toBe(2);
  });
});

describe("groupByBranch", () => {
  it("按 branchId 分组，null 归入 none 且名称兜底", () => {
    const groups = groupByBranch([
      makeEvent({ id: "a", branchId: 10, branchName: "main" }),
      makeEvent({ id: "b", branchId: 10, branchName: "main" }),
      makeEvent({ id: "c", branchId: null, branchName: "" })
    ]);
    expect(groups).toHaveLength(2);
    expect(groups[0]).toMatchObject({ branchId: 10, branchName: "main" });
    expect(groups[0].events.map(e => e.id)).toEqual(["a", "b"]);
    expect(groups[1]).toMatchObject({
      branchId: null,
      branchName: "未关联分支"
    });
  });
});

describe("buildHeatmap", () => {
  const days = [
    { date: "2026-10-13", weekday: "周二", isToday: true, isPast: false },
    { date: "2026-10-14", weekday: "周三", isToday: false, isPast: false }
  ];

  it("rows = 入参时刻，counts 长度 = 入参天数", () => {
    const rows = buildHeatmap([], days, ["08:00", "09:00"]);
    expect(rows.map(r => r.time)).toEqual(["08:00", "09:00"]);
    rows.forEach(r => expect(r.counts).toEqual([0, 0]));
  });

  it("计数落在 [时刻][日期] 交叉格", () => {
    const rows = buildHeatmap(
      [
        makeEvent({ date: "2026-10-13", time: "08:00" }),
        makeEvent({ date: "2026-10-13", time: "08:00" }),
        makeEvent({ date: "2026-10-14", time: "09:00" })
      ],
      days,
      ["08:00", "09:00"]
    );
    expect(rows[0].counts).toEqual([2, 0]);
    expect(rows[1].counts).toEqual([0, 1]);
  });

  it("范围外日期 / 未收集时刻被忽略，不抛错", () => {
    const rows = buildHeatmap(
      [
        makeEvent({ date: "2026-11-01", time: "08:00" }),
        makeEvent({ date: "2026-10-13", time: "23:59" })
      ],
      days,
      ["08:00"]
    );
    expect(rows[0].counts).toEqual([0, 0]);
  });
});

describe("collectTimePoints", () => {
  it("去重升序；空输入返回空数组", () => {
    expect(
      collectTimePoints([
        makeEvent({ time: "18:00" }),
        makeEvent({ time: "08:00" }),
        makeEvent({ time: "08:00" })
      ])
    ).toEqual(["08:00", "18:00"]);
    expect(collectTimePoints([])).toEqual([]);
  });
});

describe("durationOf", () => {
  it("正常分钟差", () => {
    expect(durationOf("08:00", "08:30")).toBe(30);
    expect(durationOf("09:00", "10:00")).toBe(60);
  });

  it("跨零点或 end<=start 归零（后端禁止跨天时段）", () => {
    expect(durationOf("23:00", "01:00")).toBe(0);
    expect(durationOf("08:00", "08:00")).toBe(0);
    expect(durationOf("09:00", "08:00")).toBe(0);
  });
});
