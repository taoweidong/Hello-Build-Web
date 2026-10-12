<template>
  <section class="toolbar-panel wk-panel wk-enter">
    <!-- 组 1：周导航 -->
    <div class="tb-group">
      <button
        class="wk-icon-btn"
        type="button"
        aria-label="上一周"
        @click="emit('shift', -1)"
      >
        <IconifyIconOffline :icon="ArrowLeft" />
      </button>
      <span class="tb-week-range">{{ weekRangeText }}</span>
      <span class="wk-pill wk-pill--accent">第 {{ weekNumber }} 周</span>
      <button
        class="wk-icon-btn"
        type="button"
        aria-label="下一周"
        @click="emit('shift', 1)"
      >
        <IconifyIconOffline :icon="ArrowRight" />
      </button>
      <button
        class="wk-ghost-btn"
        type="button"
        :disabled="isCurrentWeek"
        @click="emit('this-week')"
      >
        本周
      </button>
      <el-select
        :model-value="selectedWeek"
        class="tb-select"
        size="small"
        placeholder="选择本周"
        @update:model-value="v => emit('update:selectedWeek', v as string)"
      >
        <template #prefix>
          <IconifyIconOffline :icon="CalendarIcon" />
        </template>
        <el-option
          v-for="w in monthWeeks"
          :key="w.value"
          :label="w.label"
          :value="w.value"
        />
      </el-select>
    </div>

    <span class="tb-divider" />

    <!-- 组 2：版本 / 分支筛选 -->
    <div class="tb-group">
      <el-select
        :model-value="versionId"
        class="tb-select"
        size="small"
        filterable
        placeholder="选择版本"
        @update:model-value="
          v => emit('update:versionId', v as number | undefined)
        "
      >
        <template #prefix>
          <IconifyIconOffline :icon="BoxIcon" />
        </template>
        <el-option
          v-for="v in versionOptions"
          :key="v.version_id"
          :label="v.version_name"
          :value="v.version_id"
        />
      </el-select>
      <el-select
        :model-value="branchFilter"
        class="tb-select"
        size="small"
        multiple
        collapse-tags
        collapse-tags-tooltip
        clearable
        placeholder="全部分支"
        @update:model-value="v => emit('update:branchFilter', v as number[])"
      >
        <template #prefix>
          <IconifyIconOffline :icon="ShareIcon" />
        </template>
        <el-option
          v-for="b in branches"
          :key="b.branch_id"
          :label="b.branch_name"
          :value="b.branch_id"
        />
      </el-select>
    </div>

    <span class="tb-divider" />

    <!-- 组 3：统计与图例 -->
    <div class="tb-group tb-stats">
      <span class="tb-stat">
        策略任务 <b>{{ stats.tasks }}</b>
      </span>
      <span class="tb-stat">
        覆盖分支 <b>{{ stats.branches }}</b>
      </span>
    </div>

    <div class="tb-group tb-legend">
      <span class="tb-legend-label">图例</span>
      <span
        v-for="b in visibleBranches"
        :key="b.branch_id"
        class="tb-legend-item"
      >
        <i
          class="wk-dot"
          :style="{
            background: branchColor(b.branch_id),
            color: branchColor(b.branch_id)
          }"
        />{{ b.branch_name }}
      </span>
      <span class="tb-legend-item">
        <i class="wk-dot wk-dot--push" style="color: var(--wk-text-3)" />推送
      </span>
    </div>
  </section>
</template>

<script setup lang="ts">
// 周报工具栏：周导航 + 版本/分支筛选 + 统计图例（业务交互与原页面一致）
import ArrowLeft from "~icons/ep/arrow-left";
import ArrowRight from "~icons/ep/arrow-right";
import CalendarIcon from "~icons/ep/calendar";
import BoxIcon from "~icons/ep/files";
import ShareIcon from "~icons/ep/share";

defineOptions({ name: "WeeklyReportToolbar" });

defineProps<{
  weekRangeText: string;
  weekNumber: number;
  isCurrentWeek: boolean;
  monthWeeks: { value: string; label: string }[];
  selectedWeek: string;
  versionId: number | undefined;
  versionOptions: { version_id: number; version_name: string }[];
  branchFilter: number[];
  branches: { branch_id: number; branch_name: string }[];
  visibleBranches: { branch_id: number; branch_name: string }[];
  stats: { tasks: number; branches: number };
  branchColor: (branchId: number) => string;
}>();

const emit = defineEmits<{
  (e: "shift", delta: number): void;
  (e: "this-week"): void;
  (e: "update:selectedWeek", value: string): void;
  (e: "update:versionId", value: number | undefined): void;
  (e: "update:branchFilter", value: number[]): void;
}>();
</script>

<style scoped lang="scss">
.toolbar-panel {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  align-items: center;
  padding: 10px 16px;
}

.tb-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.tb-divider {
  flex: none;
  width: 1px;
  height: 22px;
  background: var(--wk-grid-line-strong);
}

.tb-week-range {
  min-width: 168px;
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--wk-text-1);
  text-align: center;
}

.tb-select {
  width: 170px;
}

/* 统计与图例靠右对齐 */
.tb-stats {
  margin-left: auto;
  font-size: 12px;
  color: var(--wk-text-3);

  .tb-stat b {
    margin-left: 2px;
    font-size: 14px;
    font-variant-numeric: tabular-nums;
    color: var(--wk-text-1);
  }
}

.tb-legend {
  font-size: 12px;
  color: var(--wk-text-3);
}

.tb-legend-label {
  margin-right: 2px;
  font-weight: 600;
}

.tb-legend-item {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  white-space: nowrap;
}

@media (width <= 1200px) {
  .tb-stats {
    margin-left: 0;
  }
}

@media (width <= 768px) {
  .toolbar-panel {
    gap: 8px 10px;
  }

  .tb-divider {
    display: none;
  }

  .tb-week-range {
    min-width: 0;
  }

  .tb-select {
    width: 150px;
  }
}
</style>
