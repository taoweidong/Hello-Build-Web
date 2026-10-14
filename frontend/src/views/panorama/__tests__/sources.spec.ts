// 三源归约单测：mapStrategyEvents / mapSlotEvents / mapBorrowEvents
// 重点锁定：锚点日区间来自服务端、其余日期退化为点事件、过期惰性判定、六动作权限包口径
import { describe, expect, it } from "vitest";
import { mapBorrowEvents } from "@/views/panorama/sources/borrowSource";
import { mapSlotEvents } from "@/views/panorama/sources/slotSource";
import { mapStrategyEvents } from "@/views/panorama/sources/strategySource";
import {
  NOW,
  makeBorrowFlow,
  makeCalendar,
  makeCell,
  makeStrategy,
  makeTemplate,
  makeTimeline
} from "./fixtures";

const BRANCH_COLOR = () => "#123456";

describe("mapStrategyEvents", () => {
  const days = ["2026-10-13", "2026-10-14"];

  it("锚点日（days[0]）按 planMap 展开四阶段，时长取服务端区间", () => {
    const events = mapStrategyEvents({
      strategies: [makeStrategy()],
      days,
      planMap: new Map([[1, makeTimeline()]]),
      branchColor: BRANCH_COLOR,
      user: { role: "admin" },
      versionId: 3,
      now: NOW
    });
    const anchor = events.filter(e => e.date === "2026-10-13");
    expect(anchor.map(e => e.kind)).toEqual([
      "build",
      "smoke",
      "analysis",
      "push"
    ]);
    expect(anchor.map(e => e.durationMin)).toEqual([30, 30, 30, 20]);
    expect(anchor[0].time).toBe("08:00");
    expect(anchor[0].endTime).toBe("08:30");
  });

  it("锚点日 push 为 null 时只展开三个阶段", () => {
    const events = mapStrategyEvents({
      strategies: [makeStrategy()],
      days,
      planMap: new Map([[1, makeTimeline("2026-10-13", { push: null })]]),
      branchColor: BRANCH_COLOR,
      user: { role: "admin" },
      versionId: 3,
      now: NOW
    });
    expect(
      events.filter(e => e.date === "2026-10-13").map(e => e.kind)
    ).toEqual(["build", "smoke", "analysis"]);
  });

  it("非锚点日退化为点事件：不展开 smoke/analysis，durationMin=0", () => {
    const events = mapStrategyEvents({
      strategies: [makeStrategy({ push_start_time: "18:00" })],
      days,
      planMap: new Map([[1, makeTimeline()]]),
      branchColor: BRANCH_COLOR,
      user: { role: "admin" },
      versionId: 3,
      now: NOW
    });
    const other = events.filter(e => e.date === "2026-10-14");
    expect(other.map(e => e.kind)).toEqual(["build", "push"]);
    other.forEach(e => expect(e.durationMin).toBe(0));
  });

  it("无 push_start_time 时非锚点日只有 build 一个点事件", () => {
    const events = mapStrategyEvents({
      strategies: [makeStrategy({ push_start_time: null })],
      days,
      planMap: new Map(),
      branchColor: BRANCH_COLOR,
      user: { role: "admin" },
      versionId: 3,
      now: NOW
    });
    expect(events.map(e => `${e.date}#${e.kind}`)).toEqual([
      "2026-10-13#build",
      "2026-10-14#build"
    ]);
  });

  it("id 全局唯一：同策略每日循环，日期入 key 才能保证跨天不撞（S4 看板 :key 回归）", () => {
    const events = mapStrategyEvents({
      strategies: [makeStrategy()],
      days,
      planMap: new Map([[1, makeTimeline()]]),
      branchColor: BRANCH_COLOR,
      user: { role: "admin" },
      versionId: 3,
      now: NOW
    });
    const ids = events.map(e => e.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain("strategy:1#2026-10-13#smoke");
    expect(ids).toContain("strategy:1#2026-10-14#build");
  });

  it("点事件 color 走 branchColor 回调，锚点日阶段色走 STAGE_COLORS", () => {
    const events = mapStrategyEvents({
      strategies: [makeStrategy()],
      days,
      planMap: new Map([[1, makeTimeline()]]),
      branchColor: BRANCH_COLOR,
      user: { role: "admin" },
      versionId: 3,
      now: NOW
    });
    const point = events.find(
      e => e.date === "2026-10-14" && e.kind === "build"
    );
    expect(point?.color).toBe("#123456");
    const smoke = events.find(
      e => e.date === "2026-10-13" && e.kind === "smoke"
    );
    // STAGE_COLORS.smoke 为紫色系，与分支色不同
    expect(smoke?.color).not.toBe("#123456");
    expect(smoke?.color).toMatch(/^#|^rgb|^var\(/);
  });

  it("权限：admin 可编辑；pm 绑定本版本可编辑；pm 未绑定只能借用", () => {
    // 构建时刻须晚于 NOW（10:00），否则按过期处理拿不到编辑权
    const base = {
      strategies: [
        makeStrategy({ build_start_time: "14:00", push_start_time: "20:00" })
      ],
      days,
      planMap: new Map(),
      branchColor: BRANCH_COLOR,
      now: NOW
    };
    const admin = mapStrategyEvents({
      ...base,
      user: { role: "admin" },
      versionId: 3
    })[0];
    expect(admin.permissions).toMatchObject({
      canEdit: true,
      canBorrow: false
    });

    const pmOwn = mapStrategyEvents({
      ...base,
      user: { role: "pm", bound_version_id: 3 },
      versionId: 3
    })[0];
    expect(pmOwn.permissions).toMatchObject({
      canEdit: true,
      canBorrow: false
    });

    const pmOther = mapStrategyEvents({
      ...base,
      user: { role: "pm", bound_version_id: 9 },
      versionId: 3
    })[0];
    expect(pmOther.permissions).toMatchObject({
      canEdit: false,
      canBorrow: true
    });
  });

  it("过期事件只读：canEdit/canBorrow 同时为 false", () => {
    const events = mapStrategyEvents({
      strategies: [makeStrategy()],
      days: ["2026-10-01"],
      planMap: new Map(),
      branchColor: BRANCH_COLOR,
      user: { role: "admin" },
      versionId: 3,
      now: NOW
    });
    expect(events[0].past).toBe(true);
    expect(events[0].permissions).toMatchObject({
      canEdit: false,
      canBorrow: false
    });
  });

  it("策略来源永不给出抢占/释放/审批能力位", () => {
    const events = mapStrategyEvents({
      strategies: [makeStrategy()],
      days,
      planMap: new Map([[1, makeTimeline()]]),
      branchColor: BRANCH_COLOR,
      user: { role: "admin" },
      versionId: 3,
      now: NOW
    });
    events.forEach(e => {
      expect(e.permissions.canOccupy).toBe(false);
      expect(e.permissions.canRelease).toBe(false);
      expect(e.permissions.canReleaseOthers).toBe(false);
      expect(e.permissions.canApprove).toBe(false);
    });
  });

  it("versionId 缺省时落 null，且 pm 无法获得编辑权", () => {
    const events = mapStrategyEvents({
      strategies: [makeStrategy()],
      days,
      planMap: new Map(),
      branchColor: BRANCH_COLOR,
      user: { role: "pm", bound_version_id: 3 },
      versionId: undefined,
      now: NOW
    });
    expect(events[0].versionId).toBeNull();
    expect(events[0].permissions.canEdit).toBe(false);
  });
});

describe("mapSlotEvents", () => {
  const baseOpts = {
    calendar: makeCalendar({
      "2026-10-13": [makeCell()],
      "2026-10-14": [makeCell({ status: "reserved", booking: undefined })]
    }),
    horizonEnd: "2026-11-30",
    today: "2026-10-13",
    user: { role: "admin" as const },
    now: NOW
  };

  it("available 时段：状态/文案/权限口径", () => {
    const events = mapSlotEvents(baseOpts);
    const available = events.find(e => e.date === "2026-10-13")!;
    expect(available.status).toBe("available");
    expect(available.statusText).toBe("空闲");
    expect(available.subtitle).toBe("空闲可抢占");
    expect(available.permissions.canOccupy).toBe(true);
    expect(available.permissions.canRelease).toBe(false);
  });

  it("改期能力位：reserved 且本人或 admin 才为 true（P2-R2）", () => {
    const booked = (isMine: boolean) => ({
      ...baseOpts,
      calendar: makeCalendar({
        "2026-10-13": [
          makeCell({
            status: "reserved" as const,
            booking: {
              id: 1,
              status: "reserved" as const,
              user_name: isMine ? "我" : "他人",
              purpose: "自测",
              version_id: 3,
              version_name: "v3.2",
              branch_id: 20,
              branch_name: "release",
              is_mine: isMine,
              created_at: "2026-10-10T09:00:00"
            }
          })
        ]
      })
    });

    // 本人占用（当前用户 admin）：可释放 + 可改期
    const mine = mapSlotEvents(booked(true))[0];
    expect(mine.permissions.canRelease).toBe(true);
    expect(mine.permissions.canReschedule).toBe(true);

    // 他人占用：admin 可代改期
    expect(
      mapSlotEvents({ ...booked(false), user: { role: "admin" } })[0]
        .permissions.canReschedule
    ).toBe(true);
    // 他人占用 + 非 admin：不可改期
    expect(
      mapSlotEvents({ ...booked(false), user: { role: "builder" } })[0]
        .permissions.canReschedule
    ).toBe(false);

    // 空闲格无记录可改
    expect(mapSlotEvents(baseOpts)[0].permissions.canReschedule).toBe(false);
  });

  it("模板已被删除时跳过该格（不渲染历史记录）", () => {
    const events = mapSlotEvents({
      ...baseOpts,
      calendar: makeCalendar({ "2026-10-13": [makeCell({ template_id: 999 })] })
    });
    expect(events).toEqual([]);
  });

  it("reserved 本人：subtitle=我的抢占，可释放不可抢占", () => {
    const events = mapSlotEvents({
      ...baseOpts,
      calendar: makeCalendar({
        "2026-10-13": [
          makeCell({
            status: "reserved",
            booking: {
              id: 1,
              status: "reserved",
              user_name: "我",
              purpose: "自测",
              version_id: 3,
              version_name: "v3.2",
              branch_id: 20,
              branch_name: "release",
              is_mine: true,
              created_at: "2026-10-10T09:00:00"
            }
          })
        ]
      })
    });
    const e = events[0];
    expect(e.statusText).toBe("已抢占");
    expect(e.subtitle).toBe("我的抢占");
    expect(e.mine).toBe(true);
    expect(e.permissions).toMatchObject({
      canOccupy: false,
      canRelease: true,
      canReleaseOthers: false
    });
    expect(e.branchName).toBe("release");
    expect(e.versionName).toBe("v3.2");
  });

  it("reserved 他人：subtitle 带占用人与用途；admin 可代释放，非 admin 不可", () => {
    const cell = makeCell({
      status: "reserved",
      booking: {
        id: 2,
        status: "reserved",
        user_name: "张三",
        purpose: "集成验证",
        version_id: 3,
        version_name: "v3.2",
        branch_id: 20,
        branch_name: "release",
        is_mine: false,
        created_at: "2026-10-10T09:00:00"
      }
    });
    const adminEvents = mapSlotEvents({
      ...baseOpts,
      calendar: makeCalendar({ "2026-10-13": [cell] })
    });
    expect(adminEvents[0].subtitle).toBe("张三 · 集成验证");
    expect(adminEvents[0].permissions.canReleaseOthers).toBe(true);
    expect(adminEvents[0].permissions.canRelease).toBe(false);

    const userEvents = mapSlotEvents({
      ...baseOpts,
      calendar: makeCalendar({ "2026-10-13": [cell] }),
      user: { role: "pm" }
    });
    expect(userEvents[0].permissions.canReleaseOthers).toBe(false);
  });

  it("可抢窗口：早于 today 或晚于 horizonEnd 均不可抢占", () => {
    const calendar = makeCalendar({
      "2026-10-12": [makeCell()],
      "2026-10-13": [makeCell()],
      "2026-12-01": [makeCell()]
    });
    const events = mapSlotEvents({ ...baseOpts, calendar });
    const byDate = Object.fromEntries(events.map(e => [e.date, e]));
    expect(byDate["2026-10-12"].permissions.canOccupy).toBe(false);
    expect(byDate["2026-10-13"].permissions.canOccupy).toBe(true);
    expect(byDate["2026-12-01"].permissions.canOccupy).toBe(false);
  });

  it("过期时段不可抢占、不可释放（惰性过期，无 expired 枚举）", () => {
    const events = mapSlotEvents({
      ...baseOpts,
      calendar: makeCalendar({ "2026-10-01": [makeCell()] }),
      today: "2026-10-01"
    });
    expect(events[0].past).toBe(true);
    expect(events[0].status).toBe("available");
    expect(events[0].permissions.canOccupy).toBe(false);
  });

  it("color 直取服务端模板字段，durationMin 由模板起止推导", () => {
    const events = mapSlotEvents({
      ...baseOpts,
      calendar: makeCalendar({ "2026-10-13": [makeCell()] }, [
        makeTemplate({
          start_time: "09:30",
          end_time: "11:15",
          color: "#abcdef"
        })
      ])
    });
    expect(events[0].color).toBe("#abcdef");
    expect(events[0].time).toBe("09:30");
    expect(events[0].endTime).toBe("11:15");
    expect(events[0].durationMin).toBe(105);
  });

  it("时段来源永不给出编辑/借用/审批能力位", () => {
    mapSlotEvents(baseOpts).forEach(e => {
      expect(e.permissions.canEdit).toBe(false);
      expect(e.permissions.canBorrow).toBe(false);
      expect(e.permissions.canApprove).toBe(false);
    });
  });
});

describe("mapBorrowEvents", () => {
  it("事件锚定发起日 created_at（不臆造执行日期）", () => {
    const [e] = mapBorrowEvents({
      flows: [makeBorrowFlow()],
      user: null,
      now: NOW
    });
    expect(e.date).toBe("2026-10-13");
    expect(e.time).toBe("09:15");
    expect(e.endTime).toBe(e.time);
    expect(e.durationMin).toBe(0);
    expect(e.past).toBe(false);
    expect(e.id).toBe("borrow:500");
  });

  it("标题/副标题包含借用双方与新构建时间", () => {
    const [e] = mapBorrowEvents({
      flows: [makeBorrowFlow()],
      user: null,
      now: NOW
    });
    expect(e.title).toBe("李四 借用 主链路策略");
    expect(e.subtitle).toContain("v3.2 → v4.0/feature-x");
    expect(e.subtitle).toContain("2026-10-14T09:30:00");
    expect(e.branchName).toBe("feature-x");
  });

  it("审批权限：admin 全部可审；pm 仅来源版本匹配；其他人不可审", () => {
    const flow = makeBorrowFlow({ source_version_id: 3 });
    const admin = mapBorrowEvents({
      flows: [flow],
      user: { role: "admin", bound_version_id: 9 }
    })[0];
    expect(admin.permissions.canApprove).toBe(true);

    const pmOwn = mapBorrowEvents({
      flows: [flow],
      user: { role: "pm", bound_version_id: 3 }
    })[0];
    expect(pmOwn.permissions.canApprove).toBe(true);

    const pmOther = mapBorrowEvents({
      flows: [flow],
      user: { role: "pm", bound_version_id: 8 }
    })[0];
    expect(pmOther.permissions.canApprove).toBe(false);

    const tester = mapBorrowEvents({
      flows: [flow],
      user: { role: "tester", bound_version_id: 3 }
    })[0];
    expect(tester.permissions.canApprove).toBe(false);
  });

  it("mine 由 borrower_id 与当前用户 id 比较决定", () => {
    const flow = makeBorrowFlow({ borrower_id: 7 });
    expect(
      mapBorrowEvents({
        flows: [flow],
        user: { role: "pm", bound_version_id: 3, id: 7 }
      })[0].mine
    ).toBe(true);
    expect(
      mapBorrowEvents({
        flows: [flow],
        user: { role: "pm", bound_version_id: 3, id: 8 }
      })[0].mine
    ).toBe(false);
    expect(mapBorrowEvents({ flows: [flow], user: null })[0].mine).toBe(false);
  });

  it("撤销能力位：本人 + 待审批才为 true（P2-R1）", () => {
    // 本人发起的待审批申请
    expect(
      mapBorrowEvents({
        flows: [makeBorrowFlow({ borrower_id: 7, status: "pending" })],
        user: { role: "builder", id: 7 }
      })[0].permissions.canCancel
    ).toBe(true);

    // 非本人：即使有审批权也不能替他人撤销
    const others = mapBorrowEvents({
      flows: [makeBorrowFlow({ borrower_id: 99, status: "pending" })],
      user: { role: "admin", id: 7 }
    })[0];
    expect(others.permissions.canApprove).toBe(true);
    expect(others.permissions.canCancel).toBe(false);

    // 本人但已处理（approved/rejected/cancelled）：不可撤
    for (const status of ["approved", "rejected", "cancelled"] as const) {
      expect(
        mapBorrowEvents({
          flows: [makeBorrowFlow({ borrower_id: 7, status })],
          user: { role: "builder", id: 7 }
        })[0].permissions.canCancel
      ).toBe(false);
    }
  });

  it("状态徽标走 el-tag 语义映射，色板用 warning 语义变量", () => {
    const [e] = mapBorrowEvents({
      flows: [makeBorrowFlow()],
      user: null,
      now: NOW
    });
    expect(e.status).toBe("pending");
    expect(e.statusText).toBe("待审批");
    expect(e.color).toBe("var(--el-color-warning)");
  });

  it("借用来源永不给出编辑/抢占/释放能力位", () => {
    mapBorrowEvents({
      flows: [makeBorrowFlow()],
      user: { role: "admin" }
    }).forEach(e => {
      expect(e.permissions).toMatchObject({
        canEdit: false,
        canBorrow: false,
        canOccupy: false,
        canRelease: false,
        canReleaseOthers: false
      });
    });
  });
});

// 原 countPendingApproval 用例随死导出删除（R4-F13/F-L2）：生产红点计数由
// /panorama/todos 的 pending_approval 承载；审批权限口径已由上方
// mapBorrowEvents「审批权限」用例与 utils/business.canApproveBorrowFlow 单测锁定。
