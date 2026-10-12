/**
 * 策略周报页派生数据纯函数（由 weekly 接口数据聚合，不新增接口）。
 *
 * 全部为纯函数并单测锁定：KPI 指标、分支负载、24 小时趋势、标签云。
 * 组件只做展示，避免把聚合逻辑散落进模板。
 */
import type { WeeklyStrategy } from "@/api/types";
import { isPastSlot } from "@/utils/business";

/** KPI 指标（周报页顶部磁贴） */
export interface WeeklyKpis {
  /** 策略任务总数（受分支筛选） */
  tasks: number;
  /** 构建任务数（每条策略恒有一个构建） */
  buildTasks: number;
  /** 推送任务数（push_start_time 非空） */
  pushTasks: number;
  /** 同步推送 / 正常流程 */
  syncPush: number;
  normalPush: number;
  /** 覆盖分支数 / 分支总数 */
  branchCount: number;
  branchTotal: number;
  /** 时间点数（构建+推送去重） */
  timePoints: number;
  /** 今日待执行（构建时刻未过） */
  todayPending: number;
  /** 今日已完成（构建时刻已过） */
  todayDone: number;
  /** 最早 / 最晚构建时间（HH:mm，零填充可字典序比较） */
  earliestBuild: string;
  latestBuild: string;
}

/** 分支负载行（按任务数降序） */
export interface BranchLoadRow {
  branch_id: number;
  branch_name: string;
  /** 分支配色（由页面经 useBranchColors 注入，保持与网格一致） */
  color: string;
  total: number;
  build: number;
  push: number;
}

/** 24 小时趋势桶 */
export interface HourBucket {
  hour: number;
  build: number;
  push: number;
  total: number;
}

/** 标签云条目 */
export interface TagItem {
  text: string;
  kind: "strategy" | "template" | "branch";
  /** 出现次数（策略名恒 1，模板/分支按聚合） */
  count: number;
  /** 展示字号（px，按次数分档） */
  size: number;
}

/** 收集策略的全部时间点（构建 + 推送，去重升序） */
export function collectTimePoints(strategies: WeeklyStrategy[]): string[] {
  const times = new Set<string>();
  for (const s of strategies) {
    times.add(s.build_start_time);
    if (s.push_start_time) times.add(s.push_start_time);
  }
  return [...times].sort();
}

/** KPI 聚合：今日待执行/已完成按 isPastSlot 逐策略判定（策略每日循环） */
export function computeKpis(
  strategies: WeeklyStrategy[],
  branchTotal: number,
  today: string,
  now: Date = new Date()
): WeeklyKpis {
  const pushTasks = strategies.filter(s => !!s.push_start_time);
  const times = collectTimePoints(strategies);
  let todayDone = 0;
  for (const s of strategies) {
    if (isPastSlot(today, s.build_start_time, now)) todayDone += 1;
  }
  const buildTimes = strategies.map(s => s.build_start_time).sort();
  return {
    tasks: strategies.length,
    buildTasks: strategies.length,
    pushTasks: pushTasks.length,
    syncPush: pushTasks.filter(s => s.push_mode === "sync").length,
    normalPush: pushTasks.filter(s => s.push_mode !== "sync").length,
    branchCount: new Set(strategies.map(s => s.branch_id)).size,
    branchTotal,
    timePoints: times.length,
    todayPending: strategies.length - todayDone,
    todayDone,
    earliestBuild: buildTimes[0] ?? "--:--",
    latestBuild: buildTimes[buildTimes.length - 1] ?? "--:--"
  };
}

/**
 * 分支负载：按分支聚合任务数（构建/推送拆分），按总量降序。
 * @param colorOf 分支配色函数（页面经 useBranchColors 注入，保证与网格同色）
 */
export function computeBranchLoad(
  strategies: WeeklyStrategy[],
  branches: { branch_id: number; branch_name: string }[],
  colorOf: (branchId: number) => string
): BranchLoadRow[] {
  const rows = branches.map(b => {
    const own = strategies.filter(s => s.branch_id === b.branch_id);
    return {
      branch_id: b.branch_id,
      branch_name: b.branch_name,
      color: colorOf(b.branch_id),
      total: own.length,
      build: own.length,
      push: own.filter(s => !!s.push_start_time).length
    };
  });
  return rows
    .filter(r => r.total > 0)
    .sort((a, b) => b.total - a.total || a.branch_id - b.branch_id);
}

/**
 * 解析 "HH:mm" 的小时位：非数字、空串或越界（如 "25:00"）返回 null 由调用方跳过。
 * 旧实现 `parseInt(...) || 0` 会把非法值计入 0 点、越界值直接下标越界 TypeError（R3-F12 加守卫）。
 */
function hourOf(t: string | null | undefined): number | null {
  if (!t) return null;
  const h = Number.parseInt(t.slice(0, 2), 10);
  return Number.isInteger(h) && h >= 0 && h < 24 ? h : null;
}

/** 24 小时趋势：按小时聚合构建/推送数（小时由 HH:mm 前两位取；非法时间条目跳过不计） */
export function computeHourTrend(strategies: WeeklyStrategy[]): HourBucket[] {
  const buckets: HourBucket[] = Array.from({ length: 24 }, (_, hour) => ({
    hour,
    build: 0,
    push: 0,
    total: 0
  }));
  for (const s of strategies) {
    const h = hourOf(s.build_start_time);
    if (h !== null) {
      buckets[h].build += 1;
      buckets[h].total += 1;
    }
    if (s.push_start_time) {
      const ph = hourOf(s.push_start_time);
      if (ph !== null) {
        buckets[ph].push += 1;
        buckets[ph].total += 1;
      }
    }
  }
  return buckets;
}

/** 标签云字号分档（次数 1~5+ → 12~22px，克制不抢戏） */
function tagSize(count: number): number {
  return Math.min(22, 12 + Math.max(0, count - 1) * 2.5);
}

/**
 * 标签云：策略名（每项一次）+ 模板名 + 分支名（按出现次数加权）。
 * 排序：次数降序 → 策略优先 → 名称，取前 limit 条。
 */
export function computeTagCloud(
  strategies: WeeklyStrategy[],
  limit = 18
): TagItem[] {
  const counter = new Map<string, TagItem>();
  const bump = (text: string, kind: TagItem["kind"]) => {
    if (!text) return;
    const key = `${kind}:${text}`;
    const hit = counter.get(key);
    if (hit) hit.count += 1;
    else counter.set(key, { text, kind, count: 1, size: tagSize(1) });
  };
  for (const s of strategies) {
    bump(s.strategy_name, "strategy");
    bump(s.template_name, "template");
    bump(s.branch_name, "branch");
  }
  const kindRank: Record<TagItem["kind"], number> = {
    strategy: 0,
    template: 1,
    branch: 2
  };
  return [...counter.values()]
    .map(t => ({ ...t, size: tagSize(t.count) }))
    .sort(
      (a, b) =>
        b.count - a.count ||
        kindRank[a.kind] - kindRank[b.kind] ||
        a.text.localeCompare(b.text)
    )
    .slice(0, limit);
}
