<script setup lang="ts">
// 甘特看板组件（可复用）
// 深色主题：背景 #0a0e17、面板 #101624；阶段色：构建蓝/冒烟紫/分析橙/推送绿；冲突红色斜纹
import { ref, computed } from "vue";
import { timeToMs, parseTime, formatTime } from "@/utils/business";
import { STAGE_COLORS, type GanttPhase, type GanttRow } from "./types";

const props = withDefaults(
  defineProps<{
    rows: GanttRow[];
    rangeStart: Date;
    rangeEnd: Date;
    pixelsPerMinute: number;
    rowHeight?: number;
    headerHeight?: number;
    labelWidth?: number;
  }>(),
  {
    rowHeight: 40,
    headerHeight: 40,
    labelWidth: 240
  }
);

const emit = defineEmits<{
  (e: "click-row", row: GanttRow): void;
}>();

/** 时间 → 像素（相对 rangeStart） */
function timeToX(t: string): number {
  const offset = (timeToMs(t) - timeToMs(props.rangeStart)) / 60000;
  return Math.round(offset * props.pixelsPerMinute);
}

/** 色块背景：冲突用红色斜纹覆盖 */
function colorOf(phase: GanttPhase): string {
  if (phase.conflict) {
    return "repeating-linear-gradient(45deg, rgba(239,68,68,0.85) 0 8px, rgba(127,29,29,0.9) 8px 16px)";
  }
  return STAGE_COLORS[phase.stage] || "#64748b";
}

/** 总宽度（像素） */
const totalWidth = computed(() => {
  return Math.max(
    (timeToMs(props.rangeEnd) - timeToMs(props.rangeStart)) / 60000 *
      props.pixelsPerMinute,
    100
  );
});

/** 每小时刻度 */
const hourMarks = computed(() => {
  const marks: Date[] = [];
  const start = new Date(parseTime(props.rangeStart).getTime());
  start.setMinutes(0, 0, 0);
  const end = new Date(parseTime(props.rangeEnd).getTime());
  let cur = start.getTime();
  while (cur <= end.getTime()) {
    marks.push(new Date(cur));
    cur += 3600 * 1000;
  }
  return marks;
});

/** 悬停提示 */
const tip = ref<{
  x: number;
  y: number;
  title: string;
  lines: string[];
} | null>(null);

function showTip(event: MouseEvent, phase: GanttPhase) {
  const stageLabel: Record<string, string> = {
    build: "构建",
    smoke: "冒烟",
    analysis: "人工分析",
    push: "推送"
  };
  const lines = [
    `开始：${formatTime(phase.start, "MM-DD HH:mm")}`,
    `结束：${formatTime(phase.end, "MM-DD HH:mm")}`
  ];
  if (phase.status) lines.push(`状态：${phase.statusLabel || phase.status}`);
  if (phase.conflict) lines.push("⚠ 时间冲突");
  tip.value = {
    x: event.clientX + 14,
    y: event.clientY + 14,
    title: stageLabel[phase.stage] || phase.stage,
    lines
  };
}

function hideTip() {
  tip.value = null;
}
</script>

<template>
  <div class="gantt-wrap">
    <div class="gantt-scroll">
      <div class="gantt-body">
        <!-- 顶部时间轴刻度 -->
        <div class="gantt-header" :style="{ height: headerHeight + 'px' }">
          <div class="gantt-label-col" :style="{ width: labelWidth + 'px' }">
            <span class="gantt-phase-flag">阶段</span>
          </div>
          <div class="gantt-ruler" :style="{ width: totalWidth + 'px' }">
            <div
              v-for="h in hourMarks"
              :key="h.getTime()"
              class="gantt-hour"
              :style="{ left: (timeToMs(h) - timeToMs(rangeStart)) / 60000 * pixelsPerMinute + 'px' }"
            >
              <span>{{ formatTime(h, "HH:mm") }}</span>
            </div>
          </div>
        </div>

        <!-- 数据行 -->
        <div
          v-for="(row, i) in rows"
          :key="row.id"
          class="gantt-row"
          :class="[row.type, { clickable: row.type === 'strategy' }]"
          :style="{ top: headerHeight + i * rowHeight + 'px', height: rowHeight + 'px' }"
          @click="row.type === 'strategy' && emit('click-row', row)"
        >
          <div
            class="gantt-label-col"
            :class="{ 'group-label': row.type === 'group' }"
            :style="{ width: labelWidth + 'px' }"
          >
            <span class="gantt-label-text">{{ row.label }}</span>
          </div>
          <div class="gantt-track" :style="{ width: totalWidth + 'px' }">
            <div
              v-for="p in row.phases"
              :key="p.key"
              class="phase"
              :class="{ conflict: p.conflict }"
              :style="{
                left: timeToX(p.start) + 'px',
                width: Math.max(timeToX(p.end) - timeToX(p.start), 3) + 'px',
                background: colorOf(p)
              }"
              @mouseenter="showTip($event, p)"
              @mouseleave="hideTip"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 悬停详情卡片 -->
    <div
      v-if="tip"
      class="gantt-tip"
      :style="{ left: tip.x + 'px', top: tip.y + 'px' }"
    >
      <div class="tip-title">{{ tip.title }}</div>
      <div v-for="l in tip.lines" :key="l" class="tip-line">{{ l }}</div>
    </div>
  </div>
</template>

<style scoped>
.gantt-wrap {
  position: relative;
  background: #101624;
  border: 1px solid #1e293b;
  border-radius: 8px;
  overflow: hidden;
}
.gantt-scroll {
  overflow-x: auto;
  overflow-y: auto;
}
.gantt-body {
  position: relative;
  min-width: max-content;
}
.gantt-header {
  display: flex;
  position: sticky;
  top: 0;
  z-index: 3;
  background: #0a0e17;
  border-bottom: 1px solid #1e293b;
}
.gantt-label-col {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  padding: 0 12px;
  box-sizing: border-box;
  border-right: 1px solid #1e293b;
  background: #0a0e17;
  color: #94a3b8;
  font-size: 12px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.gantt-phase-flag {
  color: #64748b;
}
.gantt-ruler {
  position: relative;
  height: 100%;
}
.gantt-hour {
  position: absolute;
  top: 0;
  bottom: 0;
  border-left: 1px solid #1e293b;
  color: #64748b;
  font-size: 11px;
  padding: 4px 4px 0;
  white-space: nowrap;
}
.gantt-row {
  position: absolute;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  border-bottom: 1px solid #121a2a;
}
.gantt-row.group {
  background: #0a0e17;
}
.gantt-row.strategy {
  background: #101624;
}
.gantt-row.strategy.clickable {
  cursor: pointer;
}
.gantt-row.strategy.clickable:hover {
  background: #16203a;
}
.gantt-label-text {
  font-weight: 500;
}
.group-label .gantt-label-text {
  color: #e2e8f0;
  font-weight: 600;
}
.gantt-track {
  position: relative;
  height: 100%;
  flex-shrink: 0;
}
.phase {
  position: absolute;
  top: 8px;
  bottom: 8px;
  border-radius: 4px;
  cursor: default;
  box-sizing: border-box;
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.phase.conflict {
  border-color: #ef4444;
}
.gantt-tip {
  position: fixed;
  z-index: 9999;
  background: #0a0e17;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 8px 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  pointer-events: none;
  max-width: 260px;
}
.tip-title {
  color: #e2e8f0;
  font-weight: 600;
  margin-bottom: 4px;
}
.tip-line {
  color: #94a3b8;
  font-size: 12px;
  line-height: 1.6;
}
</style>