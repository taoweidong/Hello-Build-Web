<script setup lang="ts">
// 甘特看板组件（基于 @infectoone/vue-ganttastic，与 pure-admin 示例保持一致）
// 浅色主题：文本 #303133、轨道 #fff、悬停高亮 #eff6ff；阶段色复用 STAGE_COLORS；冲突红色斜纹
import { computed } from "vue";
import {
  GGanttChart,
  GGanttRow,
  type GanttBarObject
} from "@infectoone/vue-ganttastic";
import { dayjs } from "@/utils/business";
import { STAGE_COLORS, type GanttRow } from "./types";

const props = withDefaults(
  defineProps<{
    rows: GanttRow[];
    rangeStart: Date;
    rangeEnd: Date;
    /** 左侧标签列宽度（px） */
    labelWidth?: number;
  }>(),
  {
    labelWidth: 260
  }
);

const emit = defineEmits<{
  (e: "click-row", row: GanttRow, bar: GanttBarObject): void;
}>();

const stageLabel: Record<string, string> = {
  build: "构建",
  smoke: "冒烟",
  analysis: "人工分析",
  push: "推送"
};

/** 时间轴范围（绝对时间字符串，供 ganttastic 解析） */
const chartStart = computed(() => dayjs(props.rangeStart).format("YYYY-MM-DD HH:mm"));
const chartEnd = computed(() => dayjs(props.rangeEnd).format("YYYY-MM-DD HH:mm"));

/** 浅色主题配色（时间轴/标签列浅灰底，与 pure-admin 示例视觉一致） */
const colorScheme = {
  primary: "#e9edf2",
  secondary: "#e0e5eb",
  ternary: "#f2f4f7",
  quartenary: "#eaeef2",
  hoverHighlight: "#eff6ff",
  markerCurrentTime: "#ef4444",
  text: "#303133",
  background: "#ffffff"
};

/** GanttRow → ganttastic 行/色块 */
const ganttRows = computed(() =>
  props.rows.map(row => ({
    id: row.id,
    label: row.label,
    bars: row.phases.map(p => ({
      // bar-start / bar-end 字段名（与 pure-admin 示例一致）
      beginDate: dayjs(p.start).format("YYYY-MM-DD HH:mm"),
      endDate: dayjs(p.end).format("YYYY-MM-DD HH:mm"),
      // 携带回查信息，供 click-bar 定位原行
      rowId: row.id,
      phaseKey: p.key,
      versionName: p.versionName,
      strategyName: p.strategyName,
      ganttBarConfig: {
        id: p.key,
        label: stageLabel[p.stage] || p.stage,
        hasHandles: false,
        immobile: true,
        style: {
          background: p.conflict
            ? "repeating-linear-gradient(45deg, rgba(239,68,68,0.85) 0 8px, rgba(127,29,29,0.9) 8px 16px)"
            : STAGE_COLORS[p.stage] || "#64748b"
        }
      }
    }))
  }))
);

function onBarClick({ bar }: { bar: GanttBarObject }) {
  const row = props.rows.find(r => r.id === bar.rowId);
  if (row) emit("click-row", row, bar);
}
</script>

<template>
  <div class="gantt-ggt-wrap">
    <g-gantt-chart
      :chart-start="chartStart"
      :chart-end="chartEnd"
      precision="hour"
      date-format="YYYY-MM-DD HH:mm"
      bar-start="beginDate"
      bar-end="endDate"
      :color-scheme="colorScheme"
      :label-column-width="`${labelWidth}px`"
      grid
      @click-bar="onBarClick"
    >
      <!-- 顶部时间线：上行按天显示日期标题（同 pure-admin 示例 upper-timeunit 插槽） -->
      <template #upper-timeunit="{ date }">
        <span class="upper-day-label">{{ dayjs(date).format("YYYY-MM-DD") }}</span>
      </template>
      <g-gantt-row
        v-for="g in ganttRows"
        :key="g.id"
        :label="g.label"
        :bars="g.bars"
        highlight-on-hover
      >
        <template #bar-label="{ bar }">
          <span class="bar-label">{{ bar.ganttBarConfig.label }}</span>
        </template>
      </g-gantt-row>
    </g-gantt-chart>
  </div>
</template>

<style scoped>
.gantt-ggt-wrap {
  width: 100%;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
.bar-label {
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}
.upper-day-label {
  color: #303133;
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
}
</style>