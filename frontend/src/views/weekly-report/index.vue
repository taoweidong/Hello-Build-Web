<template>
  <div class="weekly-report wk-scope">
    <!-- 页头：标题 + 本周进度 + 角色 + 刷新 -->
    <ReportHeader
      :week-start="weekStart"
      :today="today"
      :week-range-text="weekRangeText"
      :version-name="currentVersionName"
      :can-edit="canEdit"
      :loading="loading"
      :last-loaded-at="lastLoadedAt"
      @refresh="loadWeekly"
    />

    <!-- KPI 磁贴 -->
    <KpiTiles :kpis="kpis" />

    <!-- 工具栏：周导航 + 筛选 + 图例 -->
    <WeekToolbar
      :week-range-text="weekRangeText"
      :week-number="weekNumber"
      :is-current-week="isCurrentWeek"
      :month-weeks="monthWeeks"
      :selected-week="selectedWeek"
      :version-id="versionId"
      :version-options="versionOptions"
      :branch-filter="branchFilter"
      :branches="branches"
      :visible-branches="visibleBranches"
      :stats="stats"
      :branch-color="branchColor"
      @shift="shiftWeek"
      @this-week="goThisWeek"
      @update:selected-week="v => (selectedWeek = v)"
      @update:version-id="v => (versionId = v)"
      @update:branch-filter="v => (branchFilter = v)"
    />

    <!-- 调度全景网格 -->
    <section
      class="grid-panel wk-panel wk-enter"
      style="animation-delay: 120ms"
    >
      <div class="wk-panel-head">
        <div class="wk-panel-title">
          调度全景
          <span class="wk-panel-sub">时间点 × 周一~周日 · 策略每日循环</span>
        </div>
        <div class="grid-head-extra">
          <span class="wk-pill wk-pill--mint"
            >今日待执行 {{ kpis.todayPending }}</span
          >
          <span class="grid-hint">
            点击芯片：{{ canEdit ? "编辑策略" : "查看详情 / 发起借用" }} ·
            过期任务仅可查看
          </span>
        </div>
      </div>
      <div v-loading="loading" class="wk-panel-body grid-body">
        <GridEmptyState v-if="emptyState" v-bind="emptyState" />
        <TechHourGrid
          v-else
          :days="weekDays"
          :rows="timeRows"
          :today="today"
          @task-click="onTaskClick"
        />
      </div>
    </section>

    <!-- 数据可视化行：分支负载 / 时段趋势 / 热点标签 -->
    <section class="viz-row">
      <BranchLoadPanel :rows="branchLoad" />
      <HourTrendPanel :buckets="hourTrend" />
      <TagCloudPanel :tags="tagCloud" />
    </section>

    <!-- 弹窗：复用周视图(New)三个业务弹窗（接口/交互完全一致，样式随系统默认） -->
    <StrategyEditDialog
      v-model="editVisible"
      :strategy="editStrategy"
      :branches="branches"
      @saved="onStrategySaved"
    />
    <StrategyBorrowDialog
      v-model="borrowVisible"
      :strategy="borrowStrategy"
      :current-version-id="versionId"
    />
    <StrategyDetailDialog v-model="detailVisible" :strategy="detailStrategy" />
  </div>
</template>

<script setup lang="ts">
// 策略周报页：weekly-new 的数据看板重塑版（浅色系统风 + 数据可视化），
// 数据逻辑复用 composables/useWeeklyPanorama，接口/交互与原页面完全一致，不新增后端调用
import { computed, ref } from "vue";
import type { StrategyItem, WeeklyStrategy } from "@/api/types";
import { useWeeklyPanorama } from "@/composables/useWeeklyPanorama";
import {
  computeBranchLoad,
  computeHourTrend,
  computeKpis,
  computeTagCloud
} from "@/utils/weeklyReport";
import ReportHeader from "./components/ReportHeader.vue";
import KpiTiles from "./components/KpiTiles.vue";
import WeekToolbar from "./components/WeekToolbar.vue";
import TechHourGrid from "./components/TechHourGrid.vue";
import GridEmptyState from "./components/GridEmptyState.vue";
import BranchLoadPanel from "./components/BranchLoadPanel.vue";
import HourTrendPanel from "./components/HourTrendPanel.vue";
import TagCloudPanel from "./components/TagCloudPanel.vue";
// 复用周视图(New)的业务弹窗（编辑 / 借用 / 只读详情），避免复制交互逻辑
import StrategyEditDialog from "@/views/weekly-new/components/StrategyEditDialog.vue";
import StrategyBorrowDialog from "@/views/weekly-new/components/StrategyBorrowDialog.vue";
import StrategyDetailDialog from "@/views/weekly-new/components/StrategyDetailDialog.vue";
import NoDataIcon from "~icons/ep/data-board";
import FolderIcon from "~icons/ep/folder-opened";
import FilterIcon from "~icons/ep/filter";

defineOptions({ name: "WeeklyReportIndex" });

const {
  today,
  weekStart,
  weekRangeText,
  weekNumber,
  isCurrentWeek,
  monthWeeks,
  selectedWeek,
  weekly,
  loading,
  lastLoadedAt,
  versionId,
  versionOptions,
  branches,
  currentVersionName,
  branchFilter,
  filteredStrategies,
  visibleBranches,
  branchColor,
  weekDays,
  timeRows,
  stats,
  canEdit,
  loadWeekly,
  shiftWeek,
  goThisWeek,
  resolveTaskClick,
  invalidateStrategyCache
} = useWeeklyPanorama();

/* ---- 看板派生数据（纯函数聚合，单测锁定） ---- */
const kpis = computed(() =>
  computeKpis(filteredStrategies.value, branches.value.length, today)
);
const branchLoad = computed(() =>
  computeBranchLoad(
    filteredStrategies.value,
    visibleBranches.value,
    branchColor
  )
);
const hourTrend = computed(() => computeHourTrend(filteredStrategies.value));
const tagCloud = computed(() => computeTagCloud(filteredStrategies.value));

/* ---- 网格空态 ---- */
const emptyState = computed(() => {
  if (!weekly.value)
    return {
      icon: NoDataIcon,
      title: "暂无数据",
      hint: "接口未返回周视图数据"
    };
  if (!branches.value.length)
    return {
      icon: FolderIcon,
      title: "该版本暂无分支",
      hint: "无法排布任务，可先前往「分支配置」添加"
    };
  if (!filteredStrategies.value.length)
    return {
      icon: FilterIcon,
      title: "所选分支暂无策略排布",
      hint: "调整分支筛选或切换版本后查看"
    };
  return null;
});

/* ---- 弹窗状态（编辑 / 借用 / 只读详情） ---- */
const editVisible = ref(false);
const editStrategy = ref<StrategyItem | null>(null);
const borrowVisible = ref(false);
const borrowStrategy = ref<(WeeklyStrategy & { version_name?: string }) | null>(
  null
);
const detailVisible = ref(false);
const detailStrategy = ref<(WeeklyStrategy & { version_name?: string }) | null>(
  null
);

async function onTaskClick(
  task: Parameters<typeof resolveTaskClick>[0],
  past: boolean
) {
  const result = await resolveTaskClick(task, past);
  if (!result) return;
  if (result.kind === "detail") {
    detailStrategy.value = result.strategy;
    detailVisible.value = true;
  } else if (result.kind === "borrow") {
    borrowStrategy.value = result.strategy;
    borrowVisible.value = true;
  } else {
    editStrategy.value = result.detail;
    editVisible.value = true;
  }
}

function onStrategySaved() {
  invalidateStrategyCache();
  loadWeekly();
}
</script>

<style lang="scss">
/* 集中样式（主题变量 / 共享面板与徽标类，浅色 EP 令牌体系） */
@use "./theme.scss";
</style>

<style scoped lang="scss">
/* 网格面板：行内弹性撑满，内容多时仅面板内滚动 */
.grid-panel {
  min-height: 0;
}

.grid-body {
  overflow: auto;
}

.grid-head-extra {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.grid-hint {
  font-size: 11px;
  color: var(--wk-text-3);
}

/* 可视化行：桌面三列 / 中屏两列（标签云通栏）/ 移动单列 */
.viz-row {
  display: grid;
  grid-template-columns: 1.1fr 1fr 1fr;
  gap: 14px;
}

@media (width <= 1200px) {
  .viz-row {
    grid-template-columns: 1fr 1fr;
  }

  .viz-row > :last-child {
    grid-column: span 2;
  }
}

@media (width <= 768px) {
  .viz-row {
    grid-template-columns: 1fr;
  }

  .viz-row > :last-child {
    grid-column: auto;
  }

  .grid-hint {
    display: none;
  }
}
</style>
