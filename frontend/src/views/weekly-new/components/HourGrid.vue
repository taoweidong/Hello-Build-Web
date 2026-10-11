<template>
  <div class="week-hour-grid">
    <!-- 表头：时段 + 周一~周日 -->
    <div class="grid-header">
      <div class="corner-cell">时段</div>
      <div
        v-for="d in days"
        :key="d.date"
        class="day-head"
        :class="{ today: d.date === today, weekend: isWeekend(d) }"
      >
        <span class="day-weekday">{{ d.weekday }}</span>
        <span class="day-date">{{ d.date.slice(5) }}</span>
        <el-tag
          v-if="d.date === today"
          size="small"
          effect="light"
          class="today-tag"
          >今天</el-tag
        >
      </div>
    </div>
    <!-- 行：小时段（仅保留有内容的行，按时间顺序） -->
    <div v-for="row in rows" :key="row.hour" class="grid-row">
      <div class="hour-label">
        <span class="hour-start">{{ hh(row.hour) }}</span>
        <span class="hour-end">–{{ hh(row.hour + 1) }}</span>
      </div>
      <div
        v-for="cell in row.cells"
        :key="cell.date"
        class="grid-cell"
        :class="{ weekend: isWeekendOf(cell.date), past: cell.date < today }"
      >
        <span
          v-if="!cell.tasks.length && !cell.slots.length"
          class="cell-empty"
        />
        <!-- 任务芯片：构建（分支色实底）/ 推送（同色虚线描边） -->
        <span
          v-for="task in cell.tasks"
          :key="task.key"
          class="task-chip"
          :class="{ push: task.kind === 'push' }"
          :style="
            task.kind === 'build'
              ? { background: task.color }
              : { borderColor: task.color, color: task.color }
          "
          :title="task.title"
        >
          <span class="task-stage">{{ task.stageLabel }}</span>
          <span class="task-name">{{ task.name }}</span>
          <span class="task-time">{{ task.time }}</span>
        </span>
        <!-- 抢占芯片：该日覆盖此小时的模板（复用 SlotChip 四态） -->
        <SlotChip
          v-for="slot in cell.slots"
          :key="'s-' + slot.entry.template_id"
          :entry="slot.entry"
          :template="slot.template"
          :past="cell.date < today"
          :aria-label="slotAria(cell.date, row.hour, slot)"
          @click="emit('slot-click', cell.date, slot.entry)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CalendarDayCell, SlotTemplateItem } from "@/api/slotBooking";
import SlotChip from "@/views/slot-booking/components/SlotChip.vue";

defineOptions({ name: "WeeklyNewHourGrid" });

export interface HourTaskItem {
  key: string;
  kind: "build" | "push";
  stageLabel: string;
  name: string;
  time: string;
  title: string;
  color: string;
}

export interface HourSlotItem {
  entry: CalendarDayCell;
  template: SlotTemplateItem;
}

export interface WeekCell {
  date: string;
  tasks: HourTaskItem[];
  slots: HourSlotItem[];
}

defineProps<{
  days: { date: string; weekday: string }[];
  /** 仅包含有内容的小时行（按时间升序） */
  rows: { hour: number; cells: WeekCell[] }[];
  today: string;
}>();

const emit = defineEmits<{
  (e: "slot-click", date: string, entry: CalendarDayCell): void;
}>();

function hh(h: number) {
  return `${String(h % 24).padStart(2, "0")}:00`;
}

function weekdayIndex(dateStr: string) {
  return (new Date(`${dateStr}T00:00:00`).getDay() + 6) % 7; // 0=周一
}

function isWeekend(d: { date: string }) {
  return weekdayIndex(d.date) >= 5;
}

function isWeekendOf(dateStr: string) {
  return weekdayIndex(dateStr) >= 5;
}

function slotAria(date: string, hour: number, slot: HourSlotItem): string {
  const t = slot.template;
  const range = `${hh(hour)}–${hh(hour + 1)}`;
  if (slot.entry.status === "reserved" && slot.entry.booking) {
    return `${date} ${range} ${t.name}，${slot.entry.booking.is_mine ? "我抢占的" : `已被 ${slot.entry.booking.user_name} 抢占`}`;
  }
  return `${date} ${range} ${t.name}，可抢占`;
}
</script>

<style scoped lang="scss">
.week-hour-grid {
  display: flex;
  flex-direction: column;
  min-width: 900px;
}

.grid-header,
.grid-row {
  display: grid;
  grid-template-columns: 96px repeat(7, minmax(0, 1fr));
}

.grid-header {
  border-bottom: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
}

.corner-cell {
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
}

.day-head {
  padding: 6px 8px;
  text-align: center;
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;

  &:last-child {
    border-right: none;
  }

  &.weekend {
    background: var(--el-fill-color-light);
  }

  &.today {
    background: var(--el-color-primary-light-9);
  }

  .day-weekday {
    font-size: 13px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  .day-date {
    font-size: 11px;
    color: var(--el-text-color-secondary);
    font-variant-numeric: tabular-nums;
  }

  .today-tag {
    transform: scale(0.85);
  }
}

.grid-row + .grid-row {
  border-top: 1px solid var(--el-border-color-lighter);
}

.hour-label {
  padding: 6px 10px;
  display: flex;
  align-items: baseline;
  gap: 2px;
  background: var(--el-fill-color-light);
  border-right: 1px solid var(--el-border-color-lighter);
  font-variant-numeric: tabular-nums;

  .hour-start {
    font-size: 13px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  .hour-end {
    font-size: 11px;
    color: var(--el-text-color-placeholder);
  }
}

.grid-cell {
  min-height: 52px;
  padding: 5px 6px;
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

/* ---- 任务芯片 ---- */
.task-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 18px;
  min-height: 20px;
  color: #fff;
  border: 1px solid transparent;
  overflow: hidden;
  white-space: nowrap;

  &.push {
    background: transparent;
    border-style: dashed;
  }

  .task-stage {
    flex: none;
    font-weight: 600;
  }

  .task-name {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .task-time {
    flex: none;
    opacity: 0.85;
    font-variant-numeric: tabular-nums;
  }
}
</style>
