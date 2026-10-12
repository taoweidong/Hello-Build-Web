<!-- 调度全景共用事件芯片：5 布局共用同一渲染口径（配色取事件自带 color） -->
<template>
  <button
    type="button"
    class="biz-clickable schedule-chip"
    :class="{
      'chip-past': event.past,
      'chip-push': event.kind === 'push'
    }"
    :style="chipStyle"
    :aria-label="ariaLabel"
    @click="emit('click', event)"
  >
    <span class="chip-title">{{ event.title }}</span>
    <span v-if="showMeta" class="chip-meta">
      {{ event.time
      }}{{ event.endTime !== event.time ? `-${event.endTime}` : "" }} ·
      {{ event.branchName || event.subtitle }}
    </span>
  </button>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { ScheduleEvent } from "../types";

const props = defineProps<{
  event: ScheduleEvent;
  /** 是否展示时间/分支副行（紧凑布局可关闭） */
  showMeta?: boolean;
}>();

const emit = defineEmits<{
  (e: "click", event: ScheduleEvent): void;
}>();

/** 芯片配色：构建/阶段取事件色，推送用虚线描边区分（沿用既有 HourGrid 表现） */
const chipStyle = computed(() => {
  if (props.event.past) return {};
  if (props.event.kind === "push") {
    return {
      border: `1px dashed ${props.event.color}`,
      color: "var(--el-text-color-regular)",
      background: "var(--el-fill-color-light)"
    };
  }
  if (props.event.source === "slot" && props.event.status === "available") {
    return {
      border: `1px solid ${props.event.color}`,
      background: "var(--el-fill-color-light)"
    };
  }
  return {
    background: props.event.color,
    // 彩底白字走 Element Plus 语义变量（不写死 hex，深浅色均不破面）
    color: "var(--el-color-white)"
  };
});

const ariaLabel = computed(() => {
  const p = props.event;
  return `${p.date} ${p.time}${p.endTime !== p.time ? `-${p.endTime}` : ""} ${p.title}（${p.statusText}）`;
});
</script>

<style scoped lang="scss">
.schedule-chip {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 4px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  font-size: 12px;
  line-height: 16px;
  text-align: left;
  cursor: pointer;
  transition: transform 0.15s ease;

  &:hover {
    transform: translateY(-1px);
  }

  &:focus-visible {
    outline: 2px solid var(--el-color-primary);
    outline-offset: 1px;
  }

  .chip-title {
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .chip-meta {
    font-size: 11px;
    opacity: 0.85;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.chip-past {
  background: var(--el-fill-color-light) !important;
  color: var(--el-text-color-placeholder) !important;
  border-color: var(--el-border-color-lighter) !important;
  text-decoration: line-through;
  cursor: default;
}
</style>
