<script setup lang="ts">
// 版本全景页（全角色只读）
// 需求：甘特图展示所有版本 → 分支 → 构建策略，支持按单日筛选（默认当天），点击策略联动执行历史
import { ref, reactive, computed, watch, onMounted } from "vue";
import { getPlan, type PlanVersion } from "@/api/plan";
import { getExecutions } from "@/api/panorama";
import type { RoundItem } from "@/api/types";
import { dayjs, formatTime } from "@/utils/business";
import GanttGanttastic from "@/components/gantt/GanttGanttastic.vue";
import {
  STAGE_COLORS,
  type GanttRow
} from "@/components/gantt/types";
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
const rows = ref<GanttRow[]>([]);
const range = reactive({ start: new Date(), end: new Date() });

/** 把 plan 数据展开为甘特行：每个「版本+分支」为一行，该分支下所有策略的色块绘制在同一行 */
function buildRows(data: PlanVersion[]) {
  const result: GanttRow[] = [];
  data.forEach(v => {
    v.branches.forEach(b => {
      const phases: GanttRow["phases"] = [];
      b.strategies.forEach(s => {
        const tl = s.timeline;
        if (!tl) return;
        if (tl.push) {
          phases.push({
            key: `${s.id}-push`,
            stage: "push",
            start: tl.push.start,
            end: tl.push.end,
            conflict: !!s.conflict
          });
        }
        phases.push(
          {
            key: `${s.id}-build`,
            stage: "build",
            start: tl.build.start,
            end: tl.build.end,
            conflict: !!s.conflict
          },
          {
            key: `${s.id}-smoke`,
            stage: "smoke",
            start: tl.smoke.start,
            end: tl.smoke.end,
            conflict: !!s.conflict
          },
          {
            key: `${s.id}-analysis`,
            stage: "analysis",
            start: tl.analysis.start,
            end: tl.analysis.end,
            conflict: !!s.conflict
          }
        );
      });
      result.push({
        id: `b-${b.branch_id}`,
        label: `${v.version_name} / ${b.branch_name}`,
        type: "strategy",
        phases
      });
    });
  });
  return result;
}

/** 根据数据计算时间轴范围（跨天连续） */
function computeRange(data: PlanVersion[]) {
  let min = Infinity;
  let max = -Infinity;
  data.forEach(v =>
    v.branches.forEach(b =>
      b.strategies.forEach(s => {
        const tl = s.timeline;
        if (!tl) return;
        const all = [tl.push, tl.build, tl.smoke, tl.analysis].filter(Boolean);
        all.forEach(p => {
          min = Math.min(min, new Date(p.start).getTime());
          max = Math.max(max, new Date(p.end).getTime());
        });
      })
    )
  );
  if (min === Infinity || max === -Infinity) {
    const d = dayjs(filter.date).startOf("day");
    min = d.subtract(6, "hour").valueOf();
    max = d.add(12, "hour").valueOf();
  } else {
    min = Math.floor((min - 2 * 3600 * 1000) / 3600000) * 3600000;
    max = Math.ceil((max + 2 * 3600 * 1000) / 3600000) * 3600000;
  }
  range.start = new Date(min);
  range.end = new Date(max);
}

async function load() {
  loading.value = true;
  try {
    const data = await getPlan({ date: filter.date });
    planData.value = data;
    rows.value = buildRows(data);
    computeRange(data);
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
const pushStatusMap: Record<string, string> = {
  pending: "待推送",
  running: "推送中",
  success: "成功",
  failed: "失败",
  skipped: "跳过"
};
const conclusionMap: Record<string, string> = {
  pending: "待录",
  pass: "通过",
  fail: "不通过"
};

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
  <div class="version-view-page">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-left">
        <span class="filter-title">时间</span>
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
    <div class="section">
      <div class="section-title">
        执行历史
        <span v-if="selectedStrategyName" class="section-sub">
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
            <el-tag
              :type="row.conclusion === 'pass' ? 'success' : row.conclusion === 'fail' ? 'danger' : 'info'"
              size="small"
            >
              {{ conclusionMap[row.conclusion] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推送" width="90">
          <template #default="{ row }">
            {{ pushStatusMap[row.push_status] || row.push_status }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.version-view-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 16px;
}
.filter-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.filter-title {
  color: #909399;
  font-size: 13px;
}
.legend {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #909399;
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
.section {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}
.section-title {
  color: #303133;
  font-weight: 600;
  margin-bottom: 12px;
}
.section-sub {
  color: #909399;
  font-weight: 400;
  font-size: 13px;
}
</style>