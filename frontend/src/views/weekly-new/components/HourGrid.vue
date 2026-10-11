<template>
  <div class="hour-grid">
    <div
      v-for="row in rows"
      :key="row.hour"
      class="hour-row"
      :class="{ past: past }"
    >
      <div class="hour-label">
        <span class="hour-start"
          >{{ String(row.hour).padStart(2, "0") }}:00</span
        >
        <span class="hour-end"
          >–{{ String((row.hour + 1) % 24).padStart(2, "0") }}:00</span
        >
      </div>
      <div class="hour-body">
        <span v-if="!row.tasks.length && !row.slots.length" class="row-empty"
          >—</span
        >
        <!-- 任务芯片：构建（分支色实底） -->
        <span
          v-for="task in row.tasks"
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
        <!-- 抢占芯片：覆盖该小时的模板（复用 SlotChip 四态） -->
        <SlotChip
          v-for="slot in row.slots"
          :key="'slot-' + slot.entry.template_id"
          :entry="slot.entry"
          :template="slot.template"
          :past="past"
          :aria-label="slotAria(row.hour, slot)"
          @click="emit('slot-click', row.hour, slot.entry)"
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

defineProps<{
  rows: { hour: number; tasks: HourTaskItem[]; slots: HourSlotItem[] }[];
  past: boolean;
}>();

const emit = defineEmits<{
  (e: "slot-click", hour: number, entry: CalendarDayCell): void;
}>();

function slotAria(hour: number, slot: HourSlotItem): string {
  const t = slot.template;
  const range = `${String(hour).padStart(2, "0")}:00–${String((hour + 1) % 24).padStart(2, "0")}:00`;
  if (slot.entry.status === "reserved" && slot.entry.booking) {
    return `${range} ${t.name}，${slot.entry.booking.is_mine ? "我抢占的" : `已被 ${slot.entry.booking.user_name} 抢占`}`;
  }
  return `${range} ${t.name}，可抢占`;
}
</script>

<style scoped lang="scss">
.hour-grid {
  display: flex;
  flex-direction: column;
}

.hour-row {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  border-bottom: 1px solid var(--el-border-color-lighter);
  min-height: 44px;

  &:last-child {
    border-bottom: none;
  }

  &.past {
    opacity: 0.45;
  }
}

.hour-label {
  display: flex;
  align-items: baseline;
  gap: 2px;
  padding: 6px 10px;
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

.hour-body {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 5px 10px;
  min-width: 0;
}

.row-empty {
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}

/* ---- 任务芯片 ---- */
.task-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 18px;
  min-height: 24px;
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
