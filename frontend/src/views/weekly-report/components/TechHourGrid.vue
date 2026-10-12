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
        <el-tag
          v-if="d.date === today"
          size="small"
          effect="light"
          class="tg-today-pill"
          >今天</el-tag
        >
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
          today: cell.date === today
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
          :style="
            cell.past
              ? undefined
              : task.kind === 'build'
                ? { background: task.color }
                : { borderColor: task.color, color: task.color }
          "
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
// 周报调度网格（时间点 × 周一~周日）：视觉与原 HourGrid 保持一致（浅色 + EP 令牌），
// 交互完全不变；构建 = 分支色实底白字；推送 = 分支色虚线描边透明底；过期 = 置灰删除线仅可查看
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

/* ---- 表头（对齐 HourGrid：浅灰底 + 下边框） ---- */
.tg-header {
  position: sticky;
  top: 0;
  z-index: 2;
  flex: none;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color);
}

.tg-corner {
  display: flex;
  align-items: center;
  justify-content: center;
  border-right: 1px solid var(--el-border-color-lighter);
}

.tg-corner-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}

.tg-day {
  display: flex;
  flex-direction: column;
  gap: 1px;
  align-items: center;
  justify-content: center;
  padding: 6px 4px;
  border-right: 1px solid var(--el-border-color-lighter);

  &:last-child {
    border-right: none;
  }

  &.weekend {
    background: var(--el-fill-color-light);
  }

  /* 今天列：主色淡底（EP primary-light-9） */
  &.today {
    background: var(--el-color-primary-light-9);
  }
}

.tg-weekday {
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}

.tg-date {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.tg-today-pill {
  transform: scale(0.85);
}

/* ---- 行 ---- */
.tg-row {
  flex: 1 0 auto;
  min-height: 54px;
}

.tg-row + .tg-row {
  border-top: 1px solid var(--el-border-color-lighter);
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
  color: var(--el-text-color-primary);
  white-space: nowrap;
  background: var(--el-fill-color-light);
  border-right: 1px solid var(--el-border-color-lighter);
}

/* 时刻左侧主色小点（无光晕） */
.tg-time-dot {
  flex: none;
  width: 5px;
  height: 5px;
  background: var(--wk-accent);
  border-radius: 50%;
}

.tg-cell {
  display: flex;
  flex-direction: column;
  gap: 5px;
  justify-content: center;
  min-width: 0;
  padding: 5px 7px;
  border-right: 1px solid var(--el-border-color-lighter);

  &:last-child {
    border-right: none;
  }

  &.weekend {
    background: var(--el-fill-color-lighter);
  }

  /* 今天列：主色淡底，纵向贯通 */
  &.today {
    background: var(--el-color-primary-light-9);
  }
}

/* ---- 任务芯片（对齐 HourGrid 视觉） ---- */
.tg-chip {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 2px;
  justify-content: center;
  width: 100%;
  min-height: 44px;
  padding: 4px 8px;
  overflow: hidden;
  color: #fff;
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: 6px;
  transition: opacity 0.18s;

  &:hover {
    opacity: 0.85;
  }
}

/* 构建：分支色实底白字 */
.tg-chip--build {
  .tg-stage {
    background: rgb(255 255 255 / 22%);
  }
}

/* 推送：分支色虚线描边 + 透明底 */
.tg-chip--push {
  background: transparent;
  border-style: dashed;

  .tg-stage {
    background: transparent;
    border: 1px solid currentcolor;
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
  padding: 0 5px;
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
  border-radius: 3px;
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
  opacity: 0.78;
}

/* 过期历史任务：浅灰底 + 可读灰字 + 删除线，仅支持查看详情 */
.tg-chip--past {
  color: var(--el-text-color-secondary) !important;
  background: var(--el-fill-color-light) !important;
  border-color: var(--el-border-color-lighter) !important;
  border-style: solid !important;

  &:hover {
    background: var(--el-fill-color) !important;
    opacity: 1;
  }

  .tg-stage {
    color: var(--el-text-color-secondary);
    background: var(--el-fill-color);
    border-color: transparent;
  }

  .tg-name {
    color: var(--el-text-color-regular);
    text-decoration: line-through;
  }

  .tg-meta {
    color: var(--el-text-color-secondary);
    text-decoration: line-through;
    opacity: 1;
  }
}
</style>
