<template>
  <div class="weekly-new">
    <el-card shadow="never" class="main-card">
      <!-- 工具栏：周导航 + 版本选择 + 统计与图例（单行） -->
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button
            class="nav-btn"
            circle
            aria-label="上一周"
            @click="shiftWeek(-1)"
          >
            <IconifyIconOffline
              :icon="ArrowLeft"
              style="width: 14px; height: 14px"
            />
          </el-button>
          <span class="week-title">
            {{ weekRangeText }}
            <el-tag
              v-if="weekNumber > 0"
              size="small"
              effect="plain"
              class="week-tag"
            >
              第{{ weekNumber }}周
            </el-tag>
          </span>
          <el-button
            class="nav-btn"
            circle
            aria-label="下一周"
            @click="shiftWeek(1)"
          >
            <IconifyIconOffline
              :icon="ArrowRight"
              style="width: 14px; height: 14px"
            />
          </el-button>
          <el-button
            size="small"
            text
            type="primary"
            :disabled="isCurrentWeek"
            @click="goThisWeek"
          >
            本周
          </el-button>
          <el-select
            v-model="selectedWeek"
            size="small"
            placeholder="选择本周"
            style="width: 210px; margin-left: 8px"
            @change="onMonthWeekChange"
          >
            <el-option
              v-for="w in monthWeeks"
              :key="w.value"
              :value="w.value"
              :label="w.label"
            />
          </el-select>
          <el-select
            v-model="versionId"
            filterable
            size="small"
            placeholder="选择版本"
            style="width: 140px"
          >
            <el-option
              v-for="v in versionOptions"
              :key="v.version_id"
              :label="v.version_name"
              :value="v.version_id"
            />
          </el-select>
          <el-select
            v-model="branchFilter"
            multiple
            collapse-tags
            collapse-tags-tooltip
            clearable
            size="small"
            placeholder="全部分支"
            style="width: 200px; margin-left: 8px"
          >
            <el-option
              v-for="b in branches"
              :key="b.branch_id"
              :label="b.branch_name"
              :value="b.branch_id"
            />
          </el-select>
        </div>
        <div class="toolbar-right">
          <div class="toolbar-stats">
            <span>策略任务 {{ stats.tasks }}</span>
            <el-divider direction="vertical" />
            <span>覆盖分支 {{ stats.branches }}</span>
          </div>
          <el-divider direction="vertical" />
          <div class="legend">
            <span class="legend-label">图例:</span>
            <span
              v-for="b in visibleBranches"
              :key="b.branch_id"
              class="legend-item"
            >
              <i
                class="legend-dot"
                :style="{ background: branchColor(b.branch_id) }"
              />{{ b.branch_name }}
            </span>
            <span class="legend-item"
              ><i class="legend-dot legend-push" />推送</span
            >
          </div>
        </div>
      </div>

      <!-- 策略网格：时间点 × 周一~周日，自适应撑满剩余视口 -->
      <div v-loading="loading" class="grid-area">
        <el-empty v-if="!loading && !weekly" description="暂无数据" />
        <el-empty
          v-else-if="!loading && branches.length === 0"
          description="该版本暂无分支，无法排布任务"
        />
        <el-empty
          v-else-if="!loading && filteredStrategies.length === 0"
          description="所选分支暂无策略排布"
        />
        <HourGrid
          v-else
          :days="weekDays"
          :rows="timeRows"
          :today="today"
          @task-click="onTaskClick"
        />
      </div>
    </el-card>

    <!-- 策略编辑弹窗（仅内部维护人员可见点击入口） -->
    <StrategyEditDialog
      v-model="editVisible"
      :strategy="editStrategy"
      :branches="branches"
      @saved="onStrategySaved"
    />

    <!-- 策略详情 + 借用申请弹窗（无修改权限的用户） -->
    <StrategyBorrowDialog
      v-model="borrowVisible"
      :strategy="borrowStrategy"
      :current-version-id="versionId"
    />

    <!-- 只读详情弹窗（已过期的历史任务，仅支持查看） -->
    <StrategyDetailDialog v-model="detailVisible" :strategy="detailStrategy" />
  </div>
</template>

<script setup lang="ts">
// 版本策略全景(New)：以「本周 7 天为列、任务时间点为行」展示所选版本的策略排布全景
// 外部人员只读查看；内部维护人员（admin / 绑定版本的 pm）可点击任务芯片修改时间与信息
// 数据与周视图同源（GET /api/weekly），策略为每日循环，任务芯片 7 天一致
// 数据逻辑已抽取至 composables/useWeeklyPanorama（与 weekly-report 周报页共用），本页只保留展示与弹窗接线
import { ref } from "vue";
import ArrowLeft from "~icons/ep/arrow-left";
import ArrowRight from "~icons/ep/arrow-right";
import type { StrategyItem, WeeklyStrategy } from "@/api/types";
import { useWeeklyPanorama } from "@/composables/useWeeklyPanorama";
import HourGrid from "./components/HourGrid.vue";
import StrategyEditDialog from "./components/StrategyEditDialog.vue";
import StrategyBorrowDialog from "./components/StrategyBorrowDialog.vue";
import StrategyDetailDialog from "./components/StrategyDetailDialog.vue";

defineOptions({ name: "WeeklyNewIndex" });

const {
  today,
  thisWeekMonday,
  weekStart,
  weekRangeText,
  weekNumber,
  isCurrentWeek,
  monthWeeks,
  selectedWeek,
  weekly,
  loading,
  versionId,
  versionOptions,
  branches,
  strategies,
  currentVersionName,
  branchFilter,
  filteredStrategies,
  visibleBranches,
  branchColor,
  weekDays,
  timeRows,
  stats,
  canEdit,
  resolveTaskClick,
  invalidateStrategyCache,
  loadWeekly,
  shiftWeek,
  goThisWeek
} = useWeeklyPanorama();

// ---- 弹窗状态（编辑 / 借用 / 只读详情）----
/** 月周下拉：清空（value 为空）时回退本周一，避免 weekStart 被置空 */
function onMonthWeekChange(value: string) {
  weekStart.value = value || thisWeekMonday;
}

const editVisible = ref(false);
const editStrategy = ref<StrategyItem | null>(null);
// 借用弹窗（无修改权限的用户）：数据直接取自周视图策略数组（只读字段足够，且不受 /strategies 版本过滤限制）
const borrowVisible = ref(false);
const borrowStrategy = ref<(WeeklyStrategy & { version_name?: string }) | null>(
  null
);
// 只读详情弹窗（已过期的历史任务：已完成、不可修改/借用，仅支持查看）
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
  // 保存后详情缓存与周数据都需刷新（时间/启用状态可能变化）
  invalidateStrategyCache();
  loadWeekly();
}
</script>

<style scoped lang="scss">
.weekly-new {
  display: flex;
  flex-direction: column;

  /* 视口高度扣除：顶部导航+页签 81px、内容区上下边距 24px、页脚约 29px */
  height: calc(100vh - 134px);
  min-height: 520px;
}

.main-card {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;

  :deep(.el-card__body) {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
    padding: 12px 16px;
    overflow: hidden;
  }
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.week-title {
  min-width: 240px;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  text-align: center;

  .week-tag {
    margin-left: 4px;
  }
}

.toolbar-stats {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);

  .legend-item {
    display: inline-flex;
    gap: 4px;
    align-items: center;
  }

  .legend-dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 3px;

    &.legend-push {
      background: transparent;
      border: 1px dashed var(--el-text-color-secondary);
    }
  }
}

.grid-area {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  margin-top: 10px;
  overflow: auto;
}
</style>
