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
        <!-- 策略任务卡片：构建（分支色实底）/ 推送（同色虚线描边）；过期任务置灰删除线，仅可查看详情 -->
        <span
          v-for="task in cell.tasks"
          :key="task.key"
          class="task-chip"
          :class="{ push: task.kind === 'push', past: cell.past }"
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
  /** 该日该时刻是否已早于当前时间（过期历史任务：置灰删除线，仅可查看详情） */
  past: boolean;
  tasks: HourTaskItem[];
}

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
  min-width: 760px;
  min-height: 100%;
}

.grid-header,
.grid-row {
  display: grid;
  grid-template-columns: 64px repeat(7, minmax(0, 1fr));
}

.grid-header {
  flex: 0 0 auto;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color);
}

/* 表头单元格：单行不换行、水平垂直居中 */
.corner-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 4px;
  border-right: 1px solid var(--el-border-color-lighter);

  .corner-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--el-text-color-regular);
    white-space: nowrap;
  }
}

.day-head {
  display: flex;
  gap: 4px;
  align-items: center;
  justify-content: center;
  padding: 8px;
  border-right: 1px solid var(--el-border-color-lighter);

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
    font-variant-numeric: tabular-nums;
    color: var(--el-text-color-primary);
    white-space: nowrap;
  }

  .today-tag {
    transform: scale(0.85);
  }
}

/* 行：弹性拉伸分配剩余高度（撑满视口），多内容时按最小高度滚动 */
.grid-row {
  flex: 1 0 auto;
  min-height: 52px;
}

.grid-row + .grid-row {
  border-top: 1px solid var(--el-border-color-lighter);
}

/* 时段列：窄列单行居中显示精确时间点，不留空 */
.time-label {
  display: flex;
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

.grid-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  justify-content: center;
  min-width: 0;
  padding: 4px 6px;
  border-right: 1px solid var(--el-border-color-lighter);

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

/* ---- 策略任务卡片（双行：阶段徽标+策略名 / 分支·模板；填满单元格高度，日历格子式实心） ---- */
.task-chip {
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

  &:hover {
    opacity: 0.85;
  }

  &.push {
    background: transparent;
    border-style: dashed;
  }

  .chip-head {
    display: flex;
    gap: 6px;
    align-items: center;
    min-width: 0;

    .task-stage {
      flex: none;
      padding: 0 5px;
      font-size: 10px;
      font-weight: 600;
      line-height: 16px;
      background: rgb(255 255 255 / 22%);
      border-radius: 3px;
    }

    .task-name {
      overflow: hidden;
      text-overflow: ellipsis;
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
    }
  }

  .chip-meta {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    opacity: 0.78;
  }

  &.push .task-stage {
    background: transparent;
    border: 1px solid currentcolor;
  }

  /* 过期历史任务：浅灰底 + 可读灰字 + 删除线，仅支持查看详情 */
  &.past {
    color: var(--el-text-color-secondary);
    background: var(--el-fill-color-light);
    border-color: var(--el-border-color-lighter);

    &:hover {
      background: var(--el-fill-color);
      opacity: 1;
    }

    .task-stage {
      color: var(--el-text-color-secondary);
      background: var(--el-fill-color);
      border-color: transparent;
    }

    .task-name {
      color: var(--el-text-color-regular);
      text-decoration: line-through;
    }

    .chip-meta {
      color: var(--el-text-color-secondary);
      text-decoration: line-through;
      opacity: 1;
    }
  }
}
</style>
