// 甘特行构建与时间轴范围计算（plan / versionView 共用，替代两页复制实现）
// 纯函数直接导出便于单测，composable 只做响应式包装。
import { reactive, ref } from "vue";
import { dayjs, timeToMs } from "@/utils/business";
import type { PlanVersion } from "@/api/plan";
import type { GanttPhase, GanttRow } from "@/components/gantt/types";

/** plan 数据 → 甘特行：每个「版本+分支」一行，该分支下所有策略色块绘制在同一行 */
export function buildPlanRows(data: PlanVersion[]): GanttRow[] {
  const result: GanttRow[] = [];
  data.forEach(v => {
    v.branches.forEach(b => {
      const phases: GanttPhase[] = [];
      b.strategies.forEach(s => {
        const tl = s.timeline;
        if (!tl) return;
        if (tl.push) {
          phases.push({
            key: `${s.id}-push`,
            stage: "push",
            start: tl.push.start,
            end: tl.push.end,
            conflict: false, // 推送可重叠，不参与互斥标红
            versionName: v.version_name,
            strategyName: s.name
          });
        }
        phases.push(
          {
            key: `${s.id}-build`,
            stage: "build",
            start: tl.build.start,
            end: tl.build.end,
            conflict: !!s.conflict,
            versionName: v.version_name,
            strategyName: s.name
          },
          {
            key: `${s.id}-smoke`,
            stage: "smoke",
            start: tl.smoke.start,
            end: tl.smoke.end,
            conflict: !!s.conflict,
            versionName: v.version_name,
            strategyName: s.name
          },
          {
            key: `${s.id}-analysis`,
            stage: "analysis",
            start: tl.analysis.start,
            end: tl.analysis.end,
            conflict: !!s.conflict,
            versionName: v.version_name,
            strategyName: s.name
          }
        );
      });
      result.push({
        id: `b-${b.branch_id}`,
        label: `${v.version_name} / ${b.branch_name}`,
        type: "strategy",
        phases
      });
    });
  });
  return result;
}

/** 计算时间轴范围（跨天连续，上下各留 2 小时缓冲按小时取整；无数据回落当日 18:00→次日 12:00） */
export function computeTimelineRange(
  data: PlanVersion[],
  fallbackDate: string
): { start: Date; end: Date } {
  let min = Infinity;
  let max = -Infinity;
  data.forEach(v =>
    v.branches.forEach(b =>
      b.strategies.forEach(s => {
        const tl = s.timeline;
        if (!tl) return;
        const all = [tl.push, tl.build, tl.smoke, tl.analysis].filter(Boolean);
        all.forEach(p => {
          min = Math.min(min, timeToMs(p.start));
          max = Math.max(max, timeToMs(p.end));
        });
      })
    )
  );
  if (min === Infinity || max === -Infinity) {
    const d = dayjs(fallbackDate).startOf("day");
    min = d.subtract(6, "hour").valueOf();
    max = d.add(12, "hour").valueOf();
  } else {
    min = Math.floor((min - 2 * 3600 * 1000) / 3600000) * 3600000;
    max = Math.ceil((max + 2 * 3600 * 1000) / 3600000) * 3600000;
  }
  return { start: new Date(min), end: new Date(max) };
}

export function useGanttRows() {
  const rows = ref<GanttRow[]>([]);
  const range = reactive({ start: new Date(), end: new Date() });

  function buildRows(data: PlanVersion[]): GanttRow[] {
    rows.value = buildPlanRows(data);
    return rows.value;
  }

  function computeRange(data: PlanVersion[], fallbackDate: string) {
    const r = computeTimelineRange(data, fallbackDate);
    range.start = r.start;
    range.end = r.end;
  }

  return { rows, range, buildRows, computeRange };
}
