<template>
  <div class="tech-grid">
    <!-- 表头：时间角标 + 周一~周日 -->
    <div class="tg-header">
      <div class="tg-corner">
        <span class="tg-corner-text">时间</span>
      </div>
      <div
        v-for="d in days"
        :key="d.date"
        class="tg-day"
        :class="{ today: d.date === today, weekend: isWeekend(d.date) }"
      >
        <span class="tg-weekday">{{ d.weekday }}</span>
        <span class="tg-date">{{ shortDate(d.date) }}</span>
        <span v-if="d.date === today" class="tg-today-pill">今天</span>
      </div>
    </div>

    <!-- 行：任务时间点（仅保留有任务的行，按时间升序；行高弹性拉伸铺满） -->
    <div
      v-for="(row, ri) in rows"
      :key="row.time"
      class="tg-row wk-enter"
      :style="{ animationDelay: rowDelay(ri) }"
    >
      <div class="tg-time">
        <span class="tg-time-dot" />
        {{ row.time }}
      </div>
      <div
        v-for="cell in row.cells"
        :key="cell.date"
        class="tg-cell"
        :class="{
          weekend: isWeekend(cell.date),
          today: cell.date === today,
          past: cell.past
        }"
      >
        <span
          v-for="task in cell.tasks"
          :key="task.key"
          class="tg-chip"
          :class="[
            task.kind === 'push' ? 'tg-chip--push' : 'tg-chip--build',
            { 'tg-chip--past': cell.past }
          ]"
          :style="cell.past ? undefined : chipVars(task)"
          :title="cell.past ? `${task.title}（已过期，仅可查看）` : task.title"
          @click="emit('task-click', task, cell.past)"
        >
          <span class="tg-chip-top">
            <span class="tg-stage">{{ task.stageLabel }}</span>
            <span class="tg-name">{{ task.name }}</span>
          </span>
          <span class="tg-meta"
            >{{ task.branchName }} · {{ task.templateName }}</span
          >
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 周报调度网格（时间点 × 周一~周日）：深色科技风重绘，交互与原 HourGrid 一致
// 构建 = 分支色渐变实底；推送 = 分支色虚线描边 + 同色淡底；过期 = 置灰删除线仅可查看
import type { CSSProperties } from "vue";
import { hexToRgba } from "@/utils/color";
import type { HourTaskItem, WeekCell } from "@/composables/useWeeklyPanorama";

defineOptions({ name: "WeeklyReportTechGrid" });

defineProps<{
  days: { date: string; weekday: string }[];
  /** 仅包含有任务的时间点行（0:00~23:59，按时间升序，非线性铺满） */
  rows: { time: string; cells: WeekCell[] }[];
  today: string;
}>();

const emit = defineEmits<{
  (e: "task-click", task: HourTaskItem, past: boolean): void;
}>();

function weekdayIndex(dateStr: string) {
  return (new Date(`${dateStr}T00:00:00`).getDay() + 6) % 7; // 0=周一
}

function isWeekend(dateStr: string) {
  return weekdayIndex(dateStr) >= 5;
}

function shortDate(dateStr: string) {
  return dateStr.slice(5).replace("-", ".");
}

/** 行入场错峰（最多 270ms，避免长列表等待） */
function rowDelay(index: number) {
  return `${Math.min(index * 45, 270)}ms`;
}

/** 芯片主题变量：分支色 + 派生淡色（推送底色/光晕用） */
function chipVars(task: HourTaskItem): CSSProperties {
  return {
    "--chip": task.color,
    "--chip-tint": hexToRgba(task.color, 0.14)
  } as CSSProperties;
}
</script>

<style scoped lang="scss">
.tech-grid {
  display: flex;
  flex-direction: column;
  min-width: 760px;
  min-height: 100%;
}

.tg-header,
.tg-row {
  display: grid;
  grid-template-columns: 72px repeat(7, minmax(0, 1fr));
}

/* ---- 表头 ---- */
.tg-header {
  position: sticky;
  top: 0;
  z-index: 2;
  flex: none;
  background: linear-gradient(180deg, rgb(19 29 51 / 96%), rgb(15 24 44 / 88%));
  border-bottom: 1px solid var(--wk-grid-line-strong);
  backdrop-filter: blur(6px);
}

.tg-corner {
  display: flex;
  align-items: center;
  justify-content: center;
  border-right: 1px solid var(--wk-grid-line);
}

.tg-corner-text {
  font-size: 12px;
  font-weight: 600;
  color: var(--wk-text-3);
  letter-spacing: 0.08em;
}

.tg-day {
  display: flex;
  flex-direction: column;
  gap: 1px;
  align-items: center;
  padding: 8px 4px 9px;
  border-right: 1px solid var(--wk-grid-line);

  &:last-child {
    border-right: none;
  }

  &.weekend {
    background: rgb(129 140 248 / 6%);
  }

  /* 今天列：顶部青色光带 */
  &.today {
    background: rgb(56 189 248 / 8%);
    box-shadow:
      inset 0 2px 0 var(--wk-cyan),
      inset 0 0 24px -8px rgb(56 189 248 / 55%);
  }
}

.tg-weekday {
  font-size: 13px;
  font-weight: 600;
  color: var(--wk-text-1);
}

.tg-date {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--wk-text-3);
}

.tg-today-pill {
  padding: 0 7px;
  font-size: 10px;
  font-weight: 700;
  line-height: 15px;
  color: #041022;
  background: var(--wk-grad-primary);
  border-radius: 999px;
  box-shadow: 0 0 12px -2px rgb(56 189 248 / 75%);
  animation: wk-pulse 2.4s ease-in-out infinite;
}

/* ---- 行 ---- */
.tg-row {
  flex: 1 0 auto;
  min-height: 54px;
}

.tg-row + .tg-row {
  border-top: 1px solid var(--wk-grid-line);
}

.tg-row:hover .tg-cell:not(.past) {
  background: rgb(56 189 248 / 4%);
}

.tg-time {
  display: flex;
  gap: 6px;
  align-items: center;
  justify-content: center;
  padding: 4px;
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--wk-text-1);
  background: rgb(13 21 39 / 55%);
  border-right: 1px solid var(--wk-grid-line);
}

/* 时刻左侧小光点 */
.tg-time-dot {
  width: 5px;
  height: 5px;
  background: var(--wk-cyan);
  border-radius: 50%;
  box-shadow: 0 0 8px 0 rgb(56 189 248 / 85%);
}

.tg-cell {
  display: flex;
  flex-direction: column;
  gap: 5px;
  justify-content: center;
  min-width: 0;
  padding: 5px 7px;
  border-right: 1px solid var(--wk-grid-line);
  transition: background 0.2s;

  &:last-child {
    border-right: none;
  }

  &.weekend {
    background: rgb(129 140 248 / 5%);
  }

  /* 今天列：左右淡青描边，纵向贯穿 */
  &.today {
    box-shadow:
      inset 1px 0 0 rgb(56 189 248 / 30%),
      inset -1px 0 0 rgb(56 189 248 / 30%);
  }

  &.past {
    box-shadow: none;
  }
}

/* ---- 任务芯片 ---- */
.tg-chip {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 2px;
  justify-content: center;
  width: 100%;
  min-height: 46px;
  padding: 5px 9px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: 8px;
  transition:
    transform 0.18s,
    box-shadow 0.18s,
    opacity 0.18s;

  &:hover {
    transform: translateY(-1px);
  }

  &:active {
    transform: translateY(0);
  }
}

/* 构建：分支色实底 + 立体高光渐变 */
.tg-chip--build {
  color: #fff;
  text-shadow: 0 1px 2px rgb(0 0 0 / 38%);
  background-color: var(--chip);
  background-image: linear-gradient(
    160deg,
    rgb(255 255 255 / 26%),
    rgb(0 0 0 / 24%) 85%
  );
  border-color: rgb(255 255 255 / 16%);

  &:hover {
    box-shadow:
      0 8px 20px -8px var(--chip),
      0 0 0 1px var(--chip);
  }
}

/* 推送：分支色虚线描边 + 同色淡底 */
.tg-chip--push {
  color: var(--chip);
  background-color: var(--chip-tint);
  border-color: var(--chip);
  border-style: dashed;

  &:hover {
    background-color: var(--chip);
    box-shadow: 0 8px 20px -8px var(--chip);

    .tg-name,
    .tg-meta {
      color: #fff;
    }

    .tg-stage {
      color: #fff;
      border-color: rgb(255 255 255 / 70%);
    }
  }
}

.tg-chip-top {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

.tg-stage {
  flex: none;
  padding: 0 6px;
  font-size: 10px;
  font-weight: 700;
  line-height: 16px;
  letter-spacing: 0.04em;
  border: 1px solid transparent;
  border-radius: 4px;
}

.tg-chip--build .tg-stage {
  background: rgb(255 255 255 / 22%);
}

.tg-chip--push .tg-stage {
  border-color: currentcolor;
}

.tg-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.tg-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  opacity: 0.82;
}

/* 过期历史任务：置灰 + 删除线，仅支持查看详情 */
.tg-chip--past {
  color: var(--wk-text-3) !important;
  text-shadow: none;
  background: rgb(99 138 206 / 7%) !important;
  background-image: none !important;
  border-color: var(--wk-grid-line) !important;
  box-shadow: none !important;
  opacity: 0.85;
  filter: saturate(0.15);

  .tg-stage {
    color: var(--wk-text-3);
    background: rgb(99 138 206 / 10%);
    border-color: var(--wk-grid-line-strong);
  }

  .tg-name,
  .tg-meta {
    color: var(--wk-text-3);
    text-decoration: line-through;
  }
}
</style>
