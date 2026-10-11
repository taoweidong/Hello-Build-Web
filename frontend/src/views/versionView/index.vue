<script setup lang="ts">
// 版本全景页（全角色只读）
// 需求：甘特图展示所有版本 → 分支 → 构建策略，支持按单日筛选（默认当天），点击策略联动执行历史
import { ref, reactive, computed, watch, onMounted } from "vue";
import { getPlan, type PlanVersion } from "@/api/plan";
import { getExecutions } from "@/api/panorama";
import type { RoundItem } from "@/api/types";
import { dayjs, formatTime } from "@/utils/business";
import GanttGanttastic from "@/components/gantt/GanttGanttastic.vue";
import { STAGE_COLORS, type GanttRow } from "@/components/gantt/types";
import { useGanttRows } from "@/composables/useGanttRows";
import { roundConclusionMeta, pushStatusMeta } from "@/views/constants";
// 点击色块时携带的 bar 信息
import type { GanttBarObject } from "@infectoone/vue-ganttastic";

defineOptions({ name: "VersionViewIndex" });

const loading = ref(false);

// ---- 筛选条件 ----
const filter = reactive({
  date: dayjs().format("YYYY-MM-DD")
});

// ---- 数据 ----
const planData = ref<PlanVersion[]>([]);
const { rows, range, buildRows, computeRange } = useGanttRows();

async function load() {
  loading.value = true;
  try {
    const data = await getPlan({ date: filter.date });
    planData.value = data;
    rows.value = buildRows(data);
    computeRange(data, filter.date);
  } finally {
    loading.value = false;
  }
}

// ---- 点击策略色块 → 联动执行历史 ----
const selectedStrategyId = ref<number | null>(null);
const selectedStrategyName = ref("");
const executions = ref<RoundItem[]>([]);
const execLoading = ref(false);

async function onRowClick(row: GanttRow, bar: GanttBarObject) {
  // 从色块 key 解析策略 id（key 形如 `${strategyId}-${stage}`）
  const id = Number((bar?.phaseKey || "").split("-")[0]);
  if (!id) return;
  if (selectedStrategyId.value === id) {
    selectedStrategyId.value = null;
    selectedStrategyName.value = "";
    executions.value = [];
    return;
  }
  selectedStrategyId.value = id;
  // 从行标签中提取策略名（行标签为 `版本 / 分支`，策略名需从色块回查）
  selectedStrategyName.value = row.label;
  execLoading.value = true;
  try {
    executions.value = await getExecutions({
      strategy_id: id,
      from: filter.date,
      to: filter.date
    });
  } finally {
    execLoading.value = false;
  }
}

// ---- 展示辅助 ----
const legend = [
  { label: "构建", color: STAGE_COLORS.build },
  { label: "冒烟", color: STAGE_COLORS.smoke },
  { label: "人工分析", color: STAGE_COLORS.analysis },
  { label: "推送", color: STAGE_COLORS.push }
];

watch(() => filter.date, load);
onMounted(load);
</script>

<template>
  <div class="version-view-page biz-page">
    <!-- 筛选栏 -->
    <div class="biz-filter-bar">
      <div class="biz-filter-left">
        <span class="filter-title biz-sub">时间</span>
        <el-date-picker
          v-model="filter.date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          :clearable="false"
        />
        <el-button type="primary" :loading="loading" @click="load">查询</el-button>
      </div>
      <div class="legend">
        <span class="legend-label">图例</span>
        <span v-for="l in legend" :key="l.label" class="legend-item">
          <i class="legend-dot" :style="{ background: l.color }"></i>{{ l.label }}
        </span>
        <span class="legend-item">
          <i class="legend-dot conflict"></i>冲突
        </span>
      </div>
    </div>

    <!-- 甘特图：所有版本 × 分支 × 策略 -->
    <div v-loading="loading" class="gantt-container">
      <GanttGanttastic
        :rows="rows"
        :range-start="range.start"
        :range-end="range.end"
        @click-row="onRowClick"
      />
      <el-empty v-if="!loading && rows.length === 0" description="暂无版本计划数据" />
    </div>

    <!-- 执行历史联动区 -->
    <div class="section biz-card">
      <div class="section-title biz-card-title">
        执行历史
        <span v-if="selectedStrategyName" class="section-sub biz-sub">
          —— {{ selectedStrategyName }}
        </span>
      </div>
      <el-empty
        v-if="!selectedStrategyId"
        description="点击上方甘特图策略色块，查看该策略当天的执行历史"
      />
      <el-table
        v-else
        v-loading="execLoading"
        :data="executions"
        style="width: 100%"
      >
        <el-table-column label="日期" width="120">
          <template #default="{ row }">{{ row.exec_date }}</template>
        </el-table-column>
        <el-table-column label="构建" min-width="170">
          <template #default="{ row }">
            {{ formatTime(row.build_start, "MM-DD HH:mm") }} ~
            {{ formatTime(row.build_end, "HH:mm") }}
          </template>
        </el-table-column>
        <el-table-column label="冒烟" min-width="170">
          <template #default="{ row }">
            {{ formatTime(row.smoke_start, "MM-DD HH:mm") }} ~
            {{ formatTime(row.smoke_end, "HH:mm") }}
          </template>
        </el-table-column>
        <el-table-column label="分析" min-width="170">
          <template #default="{ row }">
            {{ formatTime(row.analysis_start, "MM-DD HH:mm") }} ~
            {{ formatTime(row.analysis_end, "HH:mm") }}
          </template>
        </el-table-column>
        <el-table-column label="结论" width="90">
          <template #default="{ row }">
            <el-tag :type="roundConclusionMeta(row.conclusion).type" size="small">
              {{ roundConclusionMeta(row.conclusion).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推送" width="90">
          <template #default="{ row }">
            {{ pushStatusMeta(row.push_status).text }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
/* 页面容器 / 筛选栏 / 卡片容器 / 标题复用全局 .biz-* 类 */
.legend {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.legend-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
}
.legend-dot.conflict {
  background: repeating-linear-gradient(
    45deg,
    rgba(239, 68, 68, 0.85) 0 4px,
    rgba(127, 29, 29, 0.9) 4px 8px
  );
}
.gantt-container {
  position: relative;
  min-height: 200px;
}
.section-title {
  margin-bottom: 12px;
}
</style>