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

      <span class="wk-pill" :class="canEdit ? '' : 'wk-pill--plain'">
        <i
          class="wk-dot"
          :class="canEdit ? '' : 'wk-dot--push'"
          :style="
            canEdit
              ? { background: 'var(--wk-accent)' }
              : { color: 'var(--wk-text-3)' }
          "
        />
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

/** 今天在所展示周内的下标（0-6）；今天不落在本周（历史周/未来周）时为 -1 */
const todayIndex = computed(() => {
  const diff = dayjs(props.today).diff(dayjs(props.weekStart), "day");
  return diff >= 0 && diff <= 6 ? diff : -1;
});

/** 7 天格点：已过=实心、今天=呼吸圈、未来=空心。
 * today 判定与 elapsed 解耦（R4-F4 修 F-M1）：本周周日当天 elapsed=7，
 * 原「elapsed<7」条件会把当天呼吸圈一并抹掉；「整周已过去」（今天落在周后，
 * todayIndex=-1）仍不标今天，R3-F11 语义保留。 */
const pips = computed(() =>
  Array.from({ length: 7 }, (_, i) => ({
    done: i < elapsed.value,
    today: i === todayIndex.value
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
  padding: 12px 16px;
}

.head-left {
  display: flex;
  gap: 12px;
  align-items: center;
  min-width: 0;
}

/* 徽标：主色淡底图标（与系统统计卡一致） */
.head-badge {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  font-size: 22px;
  color: var(--wk-accent);
  background: var(--wk-accent-light);
  border-radius: var(--el-border-radius-base);
}

.head-titles {
  min-width: 0;
}

.head-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--wk-text-1);
}

.head-sub {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--wk-text-3);
}

.head-version {
  font-weight: 500;
  color: var(--wk-accent);
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
  background: var(--el-fill-color-darker);
  border-radius: 999px;
}

.wp-fill {
  height: 100%;
  background: var(--wk-accent);
  border-radius: 999px;
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
    background: var(--wk-accent);
    border-color: transparent;
  }

  &.today {
    background: var(--wk-accent-light);
    border-color: var(--wk-accent);
  }
}

/* 刷新中：图标旋转（与 el-icon is-loading 一致） */
.spinning {
  animation: rh-spin 1s linear infinite;
}

@keyframes rh-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (width <= 768px) {
  .head-right {
    justify-content: space-between;
    width: 100%;
  }
}
</style>
