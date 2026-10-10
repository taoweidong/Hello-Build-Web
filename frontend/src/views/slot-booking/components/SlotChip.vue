<template>
  <button
    v-if="template"
    class="slot-chip"
    :class="[variant, { past }]"
    :style="{ '--chip-color': template.color }"
    :disabled="disabled"
    :aria-label="ariaLabel"
    @click.stop="handleClick"
  >
    <span class="chip-bar" />
    <span class="chip-time"
      >{{ template.start_time }}-{{ template.end_time }}</span
    >
    <span class="chip-body">
      <template v-if="entry.status === 'reserved' && entry.booking">
        <el-icon :size="12" class="chip-icon">
          <Star v-if="entry.booking.is_mine" />
          <Lock v-else />
        </el-icon>
        <span class="chip-user">{{ ownerLabel }}</span>
      </template>
      <template v-else>
        <span class="chip-name">{{ template.name }}</span>
      </template>
    </span>
  </button>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { CalendarDayCell, SlotTemplateItem } from "@/api/slotBooking";

defineOptions({ name: "SlotChip" });

const props = defineProps<{
  entry: CalendarDayCell;
  template?: SlotTemplateItem;
  past: boolean;
  ariaLabel?: string;
}>();

const emit = defineEmits<{
  (e: "click"): void;
}>();

/** 视图态：expired（过去日置灰）/ mine / locked / available */
const variant = computed(() => {
  if (props.entry.status === "reserved" && props.entry.booking?.is_mine)
    return "mine";
  if (props.entry.status === "reserved") return "locked";
  return "available";
});

const disabled = computed(() => props.past);

const ownerLabel = computed(() => {
  const name = props.entry.booking?.user_name ?? "";
  return props.entry.booking?.is_mine ? "我" : name.slice(0, 1) + "**";
});

function handleClick() {
  if (!disabled.value) emit("click");
}
</script>

<style scoped lang="scss">
.slot-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 2px 4px 2px 0;
  border-radius: 4px;
  border: 1px solid transparent;
  font-size: 12px;
  line-height: 18px;
  min-height: 24px;
  cursor: pointer;
  text-align: left;
  overflow: hidden;
  transition:
    transform 0.15s var(--el-transition-fade),
    box-shadow 0.15s var(--el-transition-fade);

  &:disabled {
    cursor: not-allowed;
    opacity: 0.45;
  }

  .chip-bar {
    flex: none;
    width: 3px;
    align-self: stretch;
    background: var(--chip-color, var(--el-color-primary));
    border-radius: 3px 0 0 3px;
  }

  .chip-time {
    flex: none;
    font-family: var(--el-font-family, inherit);
    color: inherit;
    white-space: nowrap;
  }

  .chip-body {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .chip-icon,
  .chip-name,
  .chip-user {
    flex: none;
  }

  &.available {
    background: var(--el-color-success-light-9);
    border-color: var(--el-color-success-light-5);
    color: var(--el-text-color-primary);

    &:not(:disabled):hover {
      transform: translateY(-1px);
      box-shadow: var(--el-box-shadow-light);
    }

    &:focus-visible {
      outline: 2px solid var(--el-color-success);
      outline-offset: 1px;
    }
  }

  &.mine {
    background: var(--el-color-primary);
    border-color: var(--el-color-primary);
    color: #fff;

    &:not(:disabled):hover {
      transform: translateY(-1px);
      box-shadow: var(--el-box-shadow-light);
    }

    &:focus-visible {
      outline: 2px solid var(--el-color-primary);
      outline-offset: 1px;
    }
  }

  &.locked {
    background: var(--el-fill-color);
    border-color: var(--el-border-color-lighter);
    color: var(--el-text-color-secondary);
    cursor: not-allowed;
  }
}

@media (max-width: 768px) {
  .slot-chip {
    min-height: 40px;
    font-size: 13px;
  }
}
</style>
