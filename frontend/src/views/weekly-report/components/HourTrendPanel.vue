<template>
  <section
    class="trend-panel wk-panel wk-enter"
    :style="{ animationDelay: '320ms' }"
  >
    <div class="wk-panel-head">
      <div class="wk-panel-title">
        时段趋势
        <span class="wk-panel-sub">全天 24 小时任务分布</span>
      </div>
      <div class="ht-legend">
        <span class="ht-legend-item"
          ><i class="ht-swatch ht-swatch--build" />构建</span
        >
        <span class="ht-legend-item"
          ><i class="ht-swatch ht-swatch--push" />推送</span
        >
      </div>
    </div>
    <div class="wk-panel-body trend-body">
      <div class="ht-chart">
        <!-- 网格线与刻度 -->
        <div class="ht-gridlines" aria-hidden="true">
          <span v-for="l in gridlines" :key="l" class="ht-gridline">
            <em class="ht-gridline-label">{{ l }}</em>
          </span>
        </div>

        <!-- 柱体 -->
        <div class="ht-bars">
          <div
            v-for="(b, hi) in buckets"
            :key="b.hour"
            class="ht-bar"
            :class="{ zero: b.total === 0, now: b.hour === nowHour }"
            :title="`${String(b.hour).padStart(2, '0')}:00 · ${b.total} 项（构建 ${b.build} / 推送 ${b.push}）`"
          >
            <div
              v-if="b.total > 0"
              class="ht-stack"
              :style="{
                height: `${(b.total / maxTotal) * 100}%`,
                animationDelay: `${hi * 28}ms`
              }"
            >
              <span
                class="ht-seg ht-seg--build"
                :style="{ height: `${(b.build / b.total) * 100}%` }"
              />
              <span
                class="ht-seg ht-seg--push"
                :style="{ height: `${(b.push / b.total) * 100}%` }"
              />
            </div>
            <i v-else class="ht-base" />
          </div>
        </div>

        <!-- 当前时刻参考线 -->
        <div class="ht-now" :style="{ left: `${nowPct}%` }">
          <span class="ht-now-label">现在</span>
        </div>

        <!-- 横轴 -->
        <div class="ht-axis">
          <span
            v-for="h in axisHours"
            :key="h"
            class="ht-axis-tick"
            :style="{ left: `${(h / 24) * 100}%` }"
          >
            {{ h }}
          </span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// 时段趋势面板：24 小时堆叠柱（构建/推送），含当前时刻参考线
import { computed } from "vue";
import type { HourBucket } from "@/utils/weeklyReport";

defineOptions({ name: "WeeklyReportHourTrend" });

const props = defineProps<{ buckets: HourBucket[] }>();

const maxTotal = computed(
  () => props.buckets.reduce((m, b) => Math.max(m, b.total), 0) || 1
);

/** 网格线刻度（最大值 / 中值） */
const gridlines = computed(() => [
  maxTotal.value,
  Math.ceil(maxTotal.value / 2)
]);

const axisHours = [0, 3, 6, 9, 12, 15, 18, 21];

/** 当前时刻（用于参考线定位；渲染时取一次，页面会话内有效） */
const now = new Date();
const nowHour = now.getHours();
const nowPct = ((nowHour + now.getMinutes() / 60) / 24) * 100;
</script>

<style scoped lang="scss">
.trend-body {
  padding: 12px 14px 10px;
}

.ht-legend {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--wk-text-3);
}

.ht-legend-item {
  display: inline-flex;
  gap: 5px;
  align-items: center;
}

.ht-swatch {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}

.ht-swatch--build {
  background: var(--wk-accent);
}

.ht-swatch--push {
  background: var(--el-color-primary-light-3);
}

.ht-chart {
  position: relative;
  height: 148px;
  padding-top: 16px;
  padding-right: 20px;
}

/* 网格线 */
.ht-gridlines {
  position: absolute;
  inset: 16px 20px 20px 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.ht-gridline {
  position: relative;
  height: 1px;
  background: var(--wk-grid-line);
}

.ht-gridline-label {
  position: absolute;
  right: 0;
  bottom: 2px;
  font-size: 9px;
  font-style: normal;
  font-variant-numeric: tabular-nums;
  color: var(--wk-text-3);
}

/* 柱体区 */
.ht-bars {
  position: absolute;
  inset: 16px 20px 20px 0;
  display: flex;
  gap: 2px;
  align-items: flex-end;
}

.ht-bar {
  position: relative;
  display: flex;
  flex: 1;
  align-items: flex-end;
  justify-content: center;
  min-width: 0;
  height: 100%;
}

.ht-stack {
  display: flex;
  flex-direction: column;
  width: 72%;
  max-width: 12px;
  min-height: 2px;
  overflow: hidden;
  border-radius: 3px 3px 0 0;
  transform-origin: center bottom;
  transition: height 0.4s;
  animation: wk-bar-grow 0.6s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}

.ht-bar:hover .ht-stack {
  filter: brightness(1.1);
}

.ht-seg {
  display: block;
  width: 100%;
  transition: height 0.4s;
}

.ht-seg--build {
  background: var(--wk-accent);
}

.ht-seg--push {
  background: var(--el-color-primary-light-3);
}

/* 无任务小时的基线点 */
.ht-base {
  width: 3px;
  height: 3px;
  background: var(--wk-grid-line-strong);
  border-radius: 50%;
}

/* 当前小时高亮底 */
.ht-bar.now::before {
  position: absolute;
  inset: 0;
  content: "";
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
}

/* 当前时刻参考线 */
.ht-now {
  position: absolute;
  inset: 12px 20px 16px 0;
  width: 0;
  pointer-events: none;
  border-left: 1px dashed var(--wk-mint);
}

.ht-now-label {
  position: absolute;
  top: -2px;
  left: 3px;
  font-size: 9px;
  font-weight: 700;
  color: var(--wk-mint);
  white-space: nowrap;
}

/* 横轴 */
.ht-axis {
  position: absolute;
  inset: auto 0 0;
  height: 20px;
}

.ht-axis-tick {
  position: absolute;
  top: 4px;
  font-size: 9px;
  font-variant-numeric: tabular-nums;
  color: var(--wk-text-3);
  transform: translateX(-50%);
}
</style>
