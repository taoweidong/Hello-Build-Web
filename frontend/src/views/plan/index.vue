<script setup lang="ts">
// 版本计划甘特看板（主视图）
// 设计文档 8.2：跨天时间轴、版本→分支→策略纵轴、阶段色块、冲突斜纹、PM 点击跳转策略编辑
import { ref, reactive, computed, watch, onMounted } from "vue";
import { useRouter } from "vue-router";
import { getPlan, type PlanVersion } from "@/api/plan";
import {
  getCurrentUser,
  timeToMs,
  dayjs
} from "@/utils/business";
import GanttChart from "@/components/gantt/GanttChart.vue";
import {
  STAGE_COLORS,
  type GanttRow,
  type GanttPhase
} from "@/components/gantt/types";

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
const rows = ref<GanttRow[]>([]);
const range = reactive({ start: new Date(), end: new Date() });
const pixelsPerMinute = ref(1);

/** 版本选择后清空分支并重载 */
function onVersionChange() {
  filter.branch_id = undefined;
  load();
}
function onBranchChange() {
  load();
}

/** 把 plan 数据展开为甘特行 */
function buildRows(data: PlanVersion[]) {
  const result: GanttRow[] = [];
  data.forEach(v => {
    // 版本分组行
    result.push({
      id: `v-${v.version_id}`,
      label: `${v.version_name}${v.pm_name ? ` · ${v.pm_name}` : ""}`,
      type: "group",
      phases: []
    });
    v.branches.forEach(b => {
      b.strategies.forEach(s => {
        const phases: GanttPhase[] = [];
        const tl = s.timeline;
        if (tl) {
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
        }
        result.push({
          id: `s-${s.id}`,
          label: `${b.branch_name} · ${s.name}`,
          type: "strategy",
          phases
        });
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
          min = Math.min(min, timeToMs(p.start));
          max = Math.max(max, timeToMs(p.end));
        });
      })
    )
  );
  if (min === Infinity || max === -Infinity) {
    // 无数据：默认当日 18:00 → 次日 12:00
    const d = dayjs(filter.date).startOf("day");
    min = d.subtract(6, "hour").valueOf();
    max = d.add(12, "hour").valueOf();
  } else {
    // 上下各留 2 小时缓冲并按小时取整
    min = Math.floor((min - 2 * 3600 * 1000) / 3600000) * 3600000;
    max = Math.ceil((max + 2 * 3600 * 1000) / 3600000) * 3600000;
  }
  range.start = new Date(min);
  range.end = new Date(max);
  // 固定总宽 1400px，自适应每分钟像素
  const minutes = (max - min) / 60000;
  pixelsPerMinute.value = Math.max(minutes > 0 ? 1400 / minutes : 1, 0.2);
}

async function load() {
  loading.value = true;
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
    computeRange(data);
  } finally {
    loading.value = false;
  }
}

// ---- PM 点击跳转策略编辑 ----
const currentUser = getCurrentUser();

function onRowClick(row: GanttRow) {
  // 仅 PM 且点击本版本策略行时可跳转
  if (currentUser?.role !== "pm") return;
  if (row.type !== "strategy") return;
  const id = row.id.replace("s-", "");
  const strategyId = Number(id);
  if (!strategyId) return;
  // 校验是否为 PM 绑定版本（从 group 上一行判断）
  const idx = rows.value.findIndex(r => r.id === row.id);
  const group = [...rows.value.slice(0, idx)].reverse().find(r => r.type === "group");
  if (group && group.label.includes(`${currentUser.bound_version_name}`)) {
    router.push({ path: "/strategy/index", query: { id: strategyId } });
  }
}

// 图例
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
  <div class="plan-page">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-left">
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
      <GanttChart
        :rows="rows"
        :range-start="range.start"
        :range-end="range.end"
        :pixels-per-minute="pixelsPerMinute"
        @click-row="onRowClick"
      />
      <el-empty v-if="!loading && rows.length === 0" description="暂无计划数据" />
    </div>
  </div>
</template>

<style scoped>
.plan-page {
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
  background: #101624;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 12px 16px;
}
.filter-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.legend {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #94a3b8;
  font-size: 12px;
}
.legend-label {
  color: #64748b;
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
</style>