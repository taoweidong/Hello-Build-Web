<template>
  <div class="month-grid">
    <div class="grid-header">
      <div v-for="w in WEEKDAYS" :key="w" class="header-cell">{{ w }}</div>
    </div>
    <div class="grid-body">
      <DayCell
        v-for="cell in cells"
        :key="cell.date"
        :date="cell.date"
        :in-month="cell.inMonth"
        :entries="days[cell.date] ?? []"
        :templates="templates"
        :today="today"
        :horizon-end="horizonEnd"
        @chip-click="
          (entry: CalendarDayCell) => emit('chip-click', cell.date, entry)
        "
        @more-click="entries => emit('more-click', cell.date, entries)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CalendarDayCell, SlotTemplateItem } from "@/api/slotBooking";
import DayCell from "./DayCell.vue";

defineOptions({ name: "SlotMonthGrid" });

const WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

defineProps<{
  cells: { date: string; inMonth: boolean }[];
  days: Record<string, CalendarDayCell[]>;
  templates: Record<number, SlotTemplateItem>;
  today: string;
  horizonEnd: string;
}>();

const emit = defineEmits<{
  (e: "chip-click", date: string, entry: CalendarDayCell): void;
  (e: "more-click", date: string, entries: CalendarDayCell[]): void;
}>();
</script>

<style scoped lang="scss">
.month-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.grid-header,
.grid-body {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
}

.header-cell {
  padding: 6px 0;
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}
</style>
