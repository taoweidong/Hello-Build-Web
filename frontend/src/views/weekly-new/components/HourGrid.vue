<template>
  <div class="week-hour-grid">
    <!-- 表头：时间 + 周一~周日（单行居中，日期并入列头不换行） -->
    <div class="grid-header">
      <div class="corner-cell">
        <span class="corner-title">时间</span>
      </div>
      <div
        v-for="d in days"
        :key="d.date"
        class="day-head"
        :class="{ today: d.date === today, weekend: isWeekend(d) }"
      >
        <span class="day-label"
          >{{ d.weekday }}({{ d.date.slice(5).replace("-", ".") }})</span
        >
        <el-tag
          v-if="d.date === today"
          size="small"
          effect="light"
          class="today-tag"
          >今天</el-tag
        >
      </div>
    </div>
    <!-- 行：任务时间点（仅保留有任务的行，按时间升序；行高自适应撑满视口） -->
    <div v-for="row in rows" :key="row.time" class="grid-row">
      <div class="time-label">{{ row.time }}</div>
      <div
        v-for="cell in row.cells"
        :key="cell.date"
        class="grid-cell"
        :class="{ weekend: isWeekendOf(cell.date) }"
      >
        <span v-if="!cell.tasks.length" class="cell-empty" />
        <!-- 策略任务卡片：构建（分支色实底）/ 推送（同色虚线描边）；维护人员可点击编辑 -->
        <span
          v-for="task in cell.tasks"
          :key="task.key"
          class="task-chip"
          :class="{ push: task.kind === 'push', clickable: editable }"
          :style="
            task.kind === 'build'
              ? { background: task.color }
              : { borderColor: task.color, color: task.color }
          "
          :title="task.title"
          @click="emit('task-click', task)"
        >
          <span class="chip-head">
            <span class="task-stage">{{ task.stageLabel }}</span>
            <span class="task-name">{{ task.name }}</span>
          </span>
          <span class="chip-meta"
            >{{ task.branchName }} · {{ task.templateName }}</span
          >
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: "WeeklyNewHourGrid" });

export interface HourTaskItem {
  key: string;
  /** 所属策略 id（维护人员点击卡片进入编辑） */
  strategyId: number;
  kind: "build" | "push";
  stageLabel: string;
  name: string;
  time: string;
  title: string;
  color: string;
  /** 卡片补充信息：所属分支、冒烟模板 */
  branchName: string;
  templateName: string;
}

export interface WeekCell {
  date: string;
  tasks: HourTaskItem[];
}

defineProps<{
  days: { date: string; weekday: string }[];
  /** 仅包含有任务的时间点行（0:00~23:59，按时间升序，非线性铺满） */
  rows: { time: string; cells: WeekCell[] }[];
  today: string;
  /** 当前用户是否可编辑（内部维护人员）：芯片显示可点击光标 */
  editable?: boolean;
}>();

const emit = defineEmits<{
  (e: "task-click", task: HourTaskItem): void;
}>();

function weekdayIndex(dateStr: string) {
  return (new Date(`${dateStr}T00:00:00`).getDay() + 6) % 7; // 0=周一
}

function isWeekend(d: { date: string }) {
  return weekdayIndex(d.date) >= 5;
}

function isWeekendOf(dateStr: string) {
  return weekdayIndex(dateStr) >= 5;
}
</script>

<style scoped lang="scss">
.week-hour-grid {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  min-width: 760px;
}

.grid-header,
.grid-row {
  display: grid;
  grid-template-columns: 64px repeat(7, minmax(0, 1fr));
}

.grid-header {
  flex: 0 0 auto;
  border-bottom: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
}

/* 表头单元格：单行不换行、水平垂直居中 */
.corner-cell {
  padding: 8px 4px;
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
  justify-content: center;

  .corner-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--el-text-color-regular);
    white-space: nowrap;
  }
}

.day-head {
  padding: 8px;
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;

  &:last-child {
    border-right: none;
  }

  &.weekend {
    background: var(--el-fill-color-light);
  }

  &.today {
    background: var(--el-color-primary-light-9);
  }

  .day-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }

  .today-tag {
    transform: scale(0.85);
  }
}

/* 行：弹性拉伸分配剩余高度，少内容时撑满视口、多内容时按最小高度滚动 */
.grid-row {
  flex: 1 0 auto;
  min-height: 52px;
}

.grid-row + .grid-row {
  border-top: 1px solid var(--el-border-color-lighter);
}

/* 时段列：窄列单行居中显示精确时间点，不留空 */
.time-label {
  padding: 4px 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
  border-right: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.grid-cell {
  padding: 4px 6px;
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  min-width: 0;

  &:last-child {
    border-right: none;
  }

  &.weekend {
    background: var(--el-fill-color-lighter);
  }
}

.cell-empty {
  min-height: 1px;
}

/* ---- 策略任务卡片（双行：阶段徽标+策略名 / 分支·模板） ---- */
.task-chip {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  width: 100%;
  padding: 4px 8px;
  border-radius: 6px;
  min-height: 44px;
  color: #fff;
  border: 1px solid transparent;
  overflow: hidden;

  &.push {
    background: transparent;
    border-style: dashed;
  }

  &.clickable {
    cursor: pointer;

    &:hover {
      opacity: 0.85;
    }
  }

  .chip-head {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;

    .task-stage {
      flex: none;
      padding: 0 5px;
      border-radius: 3px;
      font-size: 10px;
      line-height: 16px;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.22);
    }

    .task-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 12px;
      font-weight: 600;
    }
  }

  .chip-meta {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 11px;
    opacity: 0.78;
    font-variant-numeric: tabular-nums;
  }

  &.push .task-stage {
    background: transparent;
    border: 1px solid currentColor;
  }
}
</style>
