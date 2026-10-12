<template>
  <header class="report-head wk-panel wk-enter">
    <div class="head-left">
      <div class="head-badge">
        <IconifyIconOffline :icon="CalendarIcon" />
      </div>
      <div class="head-titles">
        <h2 class="head-title">策略周报</h2>
        <p class="head-sub">
          <span class="head-version">{{ versionName || "全部版本" }}</span>
          <span class="head-sep">·</span>
          <span>{{ weekRangeText }}</span>
          <span class="head-sep">·</span>
          <span class="head-updated">
            更新于 {{ lastLoadedAt ? formatClock(lastLoadedAt) : "--:--" }}
          </span>
        </p>
      </div>
    </div>

    <div class="head-right">
      <!-- 本周进度：天数进度条 + 7 天格点 -->
      <div class="week-progress">
        <div class="wp-label">
          本周进度
          <b>{{ elapsed }}/7</b>
          天
        </div>
        <div class="wp-track">
          <div class="wp-fill" :style="{ width: `${(elapsed / 7) * 100}%` }" />
        </div>
        <div class="wp-pips">
          <span
            v-for="(p, i) in pips"
            :key="i"
            class="wp-pip"
            :class="{ done: p.done, today: p.today }"
          />
        </div>
      </div>

      <span
        class="wk-pill"
        :class="canEdit ? 'wk-pill--violet' : 'wk-pill--accent'"
      >
        <i class="wk-dot" :class="canEdit ? '' : 'wk-dot--push'" />
        {{ canEdit ? "维护模式" : "只读查看" }}
      </span>

      <button
        class="wk-icon-btn"
        type="button"
        aria-label="刷新数据"
        :disabled="loading"
        @click="emit('refresh')"
      >
        <IconifyIconOffline
          :icon="RefreshIcon"
          :class="{ spinning: loading }"
        />
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
// 周报页头：标题 + 版本/周期/更新时间 + 本周进度（天数格点）+ 角色徽标 + 手动刷新
import { computed } from "vue";
import dayjs from "dayjs";
import RefreshIcon from "~icons/ep/refresh";
import CalendarIcon from "~icons/ep/calendar";

defineOptions({ name: "WeeklyReportHeader" });

const props = defineProps<{
  /** 周一起始日 YYYY-MM-DD */
  weekStart: string;
  /** 今天 YYYY-MM-DD */
  today: string;
  weekRangeText: string;
  versionName: string;
  canEdit: boolean;
  loading: boolean;
  lastLoadedAt: Date | null;
}>();

const emit = defineEmits<{ (e: "refresh"): void }>();

function formatClock(d: Date) {
  return dayjs(d).format("HH:mm");
}

/** 本周已过天数（0~7：周外取边界值） */
const elapsed = computed(() => {
  const start = dayjs(props.weekStart);
  const now = dayjs(props.today);
  if (now.isBefore(start)) return 0;
  if (now.isAfter(start.add(6, "day"))) return 7;
  return now.diff(start, "day") + 1;
});

/** 7 天格点：已过=实心、今天=呼吸圈、未来=空心 */
const pips = computed(() =>
  Array.from({ length: 7 }, (_, i) => ({
    done: i < elapsed.value,
    today: i === elapsed.value - 1 && elapsed.value > 0
  }))
);
</script>

<style scoped lang="scss">
.report-head {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
}

.head-left {
  display: flex;
  gap: 12px;
  align-items: center;
  min-width: 0;
}

.head-badge {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  font-size: 22px;
  color: #061020;
  background: var(--wk-grad-primary);
  border-radius: 12px;
  box-shadow: 0 8px 22px -8px rgb(56 189 248 / 75%);
}

.head-titles {
  min-width: 0;
}

.head-title {
  margin: 0;
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 0.02em;
  background: var(--wk-grad-text);
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.head-sub {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--wk-text-3);
}

.head-version {
  font-weight: 600;
  color: var(--wk-cyan);
}

.head-sep {
  opacity: 0.5;
}

.head-updated {
  font-variant-numeric: tabular-nums;
}

.head-right {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
}

/* 本周进度 */
.week-progress {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 10px;
  align-items: center;
}

.wp-label {
  grid-row: 1;
  grid-column: 1;
  font-size: 12px;
  color: var(--wk-text-3);

  b {
    margin: 0 1px;
    font-size: 14px;
    font-variant-numeric: tabular-nums;
    color: var(--wk-text-1);
  }
}

.wp-track {
  grid-row: 1;
  grid-column: 2;
  width: 120px;
  height: 6px;
  overflow: hidden;
  background: rgb(99 138 206 / 14%);
  border-radius: 999px;
}

.wp-fill {
  height: 100%;
  background: var(--wk-grad-primary);
  border-radius: 999px;
  box-shadow: var(--wk-glow-cyan);
  transition: width 0.6s cubic-bezier(0.22, 0.61, 0.36, 1);
}

.wp-pips {
  display: flex;
  grid-row: 2;
  grid-column: 1 / 3;
  gap: 5px;
}

.wp-pip {
  width: 100%;
  height: 4px;
  border: 1px solid var(--wk-grid-line-strong);
  border-radius: 2px;

  &.done {
    background: var(--wk-cyan);
    border-color: transparent;
  }

  &.today {
    background: rgb(56 189 248 / 25%);
    border-color: var(--wk-cyan);
    animation: wk-breathe 2.4s ease-in-out infinite;
  }
}

.spinning {
  animation: wk-pulse 1s ease-in-out infinite;
}

@media (width <= 768px) {
  .head-right {
    justify-content: space-between;
    width: 100%;
  }
}
</style>
