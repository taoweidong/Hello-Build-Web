<script setup lang="ts">
// 版本计划甘特看板（主视图）
// 设计文档 8.2：跨天时间轴、版本→分支→策略纵轴、阶段色块、冲突斜纹、PM 点击跳转策略编辑
import { ref, reactive, computed, watch, onMounted } from "vue";
import { useRouter } from "vue-router";
import { getPlan, type PlanVersion } from "@/api/plan";
import { getExecutions } from "@/api/panorama";
import { getCurrentUser, dayjs, formatTime } from "@/utils/business";
import GanttGanttastic from "@/components/gantt/GanttGanttastic.vue";
import { STAGE_COLORS, type GanttRow } from "@/components/gantt/types";
import { useGanttRows } from "@/composables/useGanttRows";
import { roundConclusionMeta, pushStatusMeta } from "@/views/constants";
// 点击色块时携带的 bar 信息
import type { GanttBarObject } from "@infectoone/vue-ganttastic";

defineOptions({ name: "PlanIndex" });

const router = useRouter();
const loading = ref(false);

// ---- 筛选条件 ----
const filter = reactive({
  date: dayjs().format("YYYY-MM-DD"),
  version_id: undefined as number | undefined,
  branch_id: undefined as number | undefined
});

// 版本/分支下拉选项（来自 /plan 返回结构）
const versionOptions = ref<Array<{ id: number; name: string; branches: Array<{ id: number; name: string }> }>>(
  []
);
const branchOptions = computed(() => {
  const v = versionOptions.value.find(item => item.id === filter.version_id);
  return v ? v.branches : [];
});

// ---- 数据 ----
const planData = ref<PlanVersion[]>([]);
const { rows, range, buildRows, computeRange } = useGanttRows();
// 点击选中的策略详情（点击色块展示）
const selectedStrategy = ref<import("@/api/plan").PlanStrategy | null>(null);
const selectedStrategyName = ref("");
const selectedVersionName = ref("");
const selectedBranchName = ref("");
const executions = ref<import("@/api/types").RoundItem[]>([]);
const detailLoading = ref(false);

/** 版本选择后清空分支并重载 */
function onVersionChange() {
  filter.branch_id = undefined;
  load();
}
function onBranchChange() {
  load();
}

async function load() {
  loading.value = true;
  // 切换筛选时清空上次选中的策略详情，避免残留过期数据
  selectedStrategy.value = null;
  selectedStrategyName.value = "";
  selectedVersionName.value = "";
  selectedBranchName.value = "";
  executions.value = [];
  try {
    const data = await getPlan({
      date: filter.date,
      version_id: filter.version_id,
      branch_id: filter.branch_id
    });
    planData.value = data;
    // 无筛选时重建版本下拉选项；有筛选时保留
    if (!filter.version_id) {
      versionOptions.value = data.map(v => ({
        id: v.version_id,
        name: v.version_name,
        branches: v.branches.map(b => ({
          id: b.branch_id,
          name: b.branch_name
        }))
      }));
    }
    rows.value = buildRows(data);
    computeRange(data, filter.date);
  } finally {
    loading.value = false;
  }
}

// ---- 点击色块：展示详情 + PM 跳转策略编辑 ----
const currentUser = getCurrentUser();

/** 加载选中策略近 7 天执行历史（带请求序号守卫，避免快速连点被旧响应覆盖） */
let detailSeq = 0;
async function loadDetailExecutions(strategyId: number) {
  const cur = ++detailSeq;
  detailLoading.value = true;
  try {
    const res = await getExecutions({
      strategy_id: strategyId,
      from: dayjs().subtract(6, "day").format("YYYY-MM-DD"),
      to: dayjs().format("YYYY-MM-DD")
    });
    if (cur !== detailSeq) return; // 过期响应丢弃
    executions.value = res;
  } finally {
    if (cur === detailSeq) detailLoading.value = false;
  }
}

/** 点击任意色块：展示策略详情（配置 + 时间线 + 执行历史），并按 PM 权限跳转策略编辑 */
async function onGanttClick(_row: GanttRow, bar: GanttBarObject) {
  // 从色块 key 解析策略 id（key 形如 `${strategyId}-${stage}`）
  const id = Number((bar?.phaseKey || "").split("-")[0]);
  if (!id) return;
  // 从 planData 定位该策略，记录详情所需信息
  outer: for (const v of planData.value) {
    for (const b of v.branches) {
      const s = b.strategies.find(x => x.id === id);
      if (s) {
        selectedVersionName.value = v.version_name;
        selectedStrategyName.value = s.name;
        selectedBranchName.value = b.branch_name;
        selectedStrategy.value = s;
        // 清空旧数据并复位 loading，避免连续点击时并发请求覆盖/提前复位
        executions.value = [];
        detailLoading.value = true;
        await loadDetailExecutions(id);
        break outer;
      }
    }
  }
  // 仅 PM 且点击本版本策略色块时可跳转
  if (currentUser?.role !== "pm") return;
  const versionName = bar?.versionName || "";
  if (versionName && versionName === currentUser.bound_version_name) {
    router.push({ path: "/strategy/index", query: { id } });
  }
}

/** 关闭详情面板 */
function closeDetail() {
  selectedStrategy.value = null;
  selectedStrategyName.value = "";
  selectedVersionName.value = "";
  selectedBranchName.value = "";
  executions.value = [];
}

// 图例
const legend = [
  { label: "构建", color: STAGE_COLORS.build },
  { label: "冒烟", color: STAGE_COLORS.smoke },
  { label: "人工分析", color: STAGE_COLORS.analysis },
  { label: "推送", color: STAGE_COLORS.push }
];

/** 详情面板时间线（对空 push 容错） */
const detailPhases = computed(() => {
  const tl = selectedStrategy.value?.timeline;
  if (!tl) return [];
  const list = [
    { stage: "push", label: "推送", t: tl.push },
    { stage: "build", label: "构建", t: tl.build },
    { stage: "smoke", label: "冒烟", t: tl.smoke },
    { stage: "analysis", label: "分析", t: tl.analysis }
  ].filter(x => x.t);
  return list.map(x => ({
    stage: x.stage,
    label: x.label,
    text: `${formatTime(x.t.start)} ~ ${formatTime(x.t.end, "HH:mm")}`,
    color: STAGE_COLORS[x.stage]
  }));
});

watch(() => filter.date, load);

onMounted(load);
</script>

<template>
  <div class="plan-page biz-page">
    <!-- 筛选栏 -->
    <div class="biz-filter-bar">
      <div class="biz-filter-left">
        <el-date-picker
          v-model="filter.date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          :clearable="false"
        />
        <el-select
          v-model="filter.version_id"
          placeholder="全部版本"
          clearable
          style="width: 160px"
          @change="onVersionChange"
        >
          <el-option
            v-for="v in versionOptions"
            :key="v.id"
            :label="v.name"
            :value="v.id"
          />
        </el-select>
        <el-select
          v-model="filter.branch_id"
          placeholder="全部分支"
          clearable
          :disabled="!filter.version_id"
          style="width: 160px"
          @change="onBranchChange"
        >
          <el-option
            v-for="b in branchOptions"
            :key="b.id"
            :label="b.name"
            :value="b.id"
          />
        </el-select>
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

    <el-alert
      v-if="currentUser?.role === 'pm'"
      title="PM 提示：点击本版本策略色块可跳转策略编辑"
      type="info"
      :closable="false"
      show-icon
      class="pm-tip"
    />

    <!-- 甘特图 -->
    <div v-loading="loading" class="gantt-container">
      <GanttGanttastic
        :rows="rows"
        :range-start="range.start"
        :range-end="range.end"
        @click-row="onGanttClick"
      />
      <el-empty v-if="!loading && rows.length === 0" description="暂无计划数据" />
    </div>

    <!-- 策略详情面板 -->
    <div v-if="selectedStrategy" class="detail-panel biz-card">
      <div class="detail-head biz-card-head">
        <span class="detail-title">策略详情：{{ selectedStrategyName }}</span>
        <span class="detail-sub">{{ selectedVersionName }} / {{ selectedBranchName }}</span>
        <el-button size="small" text @click="closeDetail">关闭</el-button>
      </div>
      <el-descriptions :column="3" size="small" border class="detail-desc">
        <el-descriptions-item label="构建开始">{{ selectedStrategy.build_start_time }}</el-descriptions-item>
        <el-descriptions-item label="推送时间">{{ selectedStrategy.push_start_time || "结论后推导" }}</el-descriptions-item>
        <el-descriptions-item label="推送模式">
          {{ selectedStrategy.push_mode === "sync" ? "同步推送冒烟" : "正常流程推送" }}
        </el-descriptions-item>
      </el-descriptions>
      <div class="detail-sec-title">时间线</div>
      <div v-if="selectedStrategy.timeline" class="detail-timeline">
        <span v-for="p in detailPhases" :key="p.stage" class="dt-item">
          <i class="dt-dot" :style="{ background: p.color }"></i>
          {{ p.label }}：{{ p.text }}
        </span>
      </div>
      <div v-else class="detail-empty">暂无时间线数据</div>
      <div class="detail-sec-title">执行历史（近 7 天）</div>
      <el-table :data="executions" v-loading="detailLoading" size="small" style="width: 100%">
        <el-table-column prop="exec_date" label="日期" width="110" />
        <el-table-column label="结论" width="90">
          <template #default="{ row }">
            <el-tag :type="roundConclusionMeta(row.conclusion).type" size="small">
              {{ roundConclusionMeta(row.conclusion).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推送" width="90">
          <template #default="{ row }">{{ pushStatusMeta(row.push_status).text }}</template>
        </el-table-column>
        <el-table-column prop="conclusion_note" label="备注" min-width="140">
          <template #default="{ row }">{{ row.conclusion_note || "-" }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.legend {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.legend-label {
  color: var(--el-text-color-secondary);
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
.pm-tip {
  margin-bottom: 0;
}
.gantt-container {
  position: relative;
  min-height: 200px;
}

/* ---- 策略详情面板 ---- */
.detail-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.detail-sub {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.detail-desc {
  margin-bottom: 12px;
}
.detail-sec-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 12px 0 8px;
}
.detail-timeline {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 8px 0;
}
.dt-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.dt-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.detail-empty {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  padding: 8px 0;
}
</style>