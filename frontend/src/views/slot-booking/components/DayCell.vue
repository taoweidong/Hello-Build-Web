<template>
  <div class="day-cell" :class="{ 'out-month': !inMonth, weekend: isWeekend }">
    <div class="day-head">
      <span class="day-num" :class="{ today: isToday }">{{
        Number(date.slice(8))
      }}</span>
    </div>
    <div v-if="!entries.length" class="day-empty">—</div>
    <div v-else class="chip-list">
      <SlotChip
        v-for="entry in visibleEntries"
        :key="entry.template_id"
        :entry="entry"
        :template="templates[entry.template_id]"
        :past="isPast"
        :aria-label="chipAria(entry)"
        @click="emit('chip-click', entry)"
      />
      <button
        v-if="hiddenCount > 0"
        class="more-btn"
        @click.stop="emit('more-click', entries)"
      >
        +{{ hiddenCount }} 更多
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { CalendarDayCell, SlotTemplateItem } from "@/api/slotBooking";
import SlotChip from "./SlotChip.vue";

defineOptions({ name: "SlotDayCell" });

const MAX_VISIBLE = 5;

const props = defineProps<{
  date: string;
  inMonth: boolean;
  entries: CalendarDayCell[];
  templates: Record<number, SlotTemplateItem>;
  today: string;
  horizonEnd: string;
}>();

const emit = defineEmits<{
  (e: "chip-click", entry: CalendarDayCell): void;
  (e: "more-click", entries: CalendarDayCell[]): void;
}>();

const isPast = computed(() => props.date < props.today);
const isToday = computed(() => props.date === props.today);
const isWeekend = computed(() => {
  const wd = new Date(`${props.date}T00:00:00`).getDay();
  return wd === 0 || wd === 6;
});
const visibleEntries = computed(() => props.entries.slice(0, MAX_VISIBLE));
const hiddenCount = computed(() =>
  Math.max(0, props.entries.length - MAX_VISIBLE)
);

function chipAria(entry: CalendarDayCell): string {
  const tpl = props.templates[entry.template_id];
  const time = tpl ? `${tpl.start_time}-${tpl.end_time}` : "";
  const name = tpl?.name ?? "时段";
  if (entry.status === "reserved" && entry.booking) {
    const who = entry.booking.is_mine
      ? "我抢占的"
      : `已被 ${entry.booking.user_name} 抢占`;
    return `${props.date} ${time} ${name}，${who}`;
  }
  return `${props.date} ${time} ${name}，可抢占`;
}
</script>

<style scoped lang="scss">
.day-cell {
  min-height: 104px;
  padding: 6px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: border-color 0.15s var(--el-transition-fade);

  &.out-month {
    opacity: 0.45;
  }

  &.weekend:not(.out-month) {
    background: var(--el-fill-color-lighter);
  }

  &:not(.out-month):hover {
    border-color: var(--el-color-primary-light-5);
  }
}

.day-head {
  display: flex;
  justify-content: flex-start;
}

.day-num {
  min-width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);

  &.today {
    background: var(--el-color-primary);
    color: #fff;
  }
}

.day-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-placeholder);
  font-size: 14px;
}

.chip-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.more-btn {
  border: none;
  background: transparent;
  color: var(--el-color-primary);
  font-size: 12px;
  text-align: left;
  padding: 2px 4px;
  cursor: pointer;
  border-radius: 4px;

  &:hover {
    background: var(--el-color-primary-light-9);
  }
}
</style>
