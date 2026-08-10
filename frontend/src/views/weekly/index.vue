<script setup lang="ts">
// 周视图看板（主视图）
// 设计文档 7.2：本周周信息 + 本月周列表 + 版本选择 + 分支×周一~周日的策略网格
// 后端 GET /api/weekly 返回扁平结构（见 WeeklyData），策略无日期字段，表示每周每天都排布
import { ref, computed, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { getWeekly } from "@/api/weekly";
import type { WeeklyData, WeeklyStrategy } from "@/api/types";
import { dayjs } from "@/utils/business";

defineOptions({ name: "WeeklyIndex" });

// 请求序号：用于丢弃过期响应（快速切换周/版本时避免旧数据覆盖新数据）
let seq = 0;

// 英文星期 → 中文 映射（模块级常量，避免每次调用重建）
const WEEKDAY_CN: Record<string, string> = {
  Monday: "周一",
  Tuesday: "周二",
  Wednesday: "周三",
  Thursday: "周四",
  Friday: "周五",
  Saturday: "周六",
  Sunday: "周日"
};

const loading = ref(false);
const data = ref<WeeklyData | null>(null);
const versionId = ref<number | undefined>(undefined);
const selectedWeek = ref("");

// 版本下拉：直接用后端返回的 versions 列表
const versionOptions = computed(() => data.value?.versions ?? []);

// 当前选中版本名（用于分支行展示；version 可能为 null）
const currentVersionName = computed(() => data.value?.version?.version_name ?? "");

// ISO 周数（后端未返回 week_number）
function isoWeek(date: Date): number {
  const d = new Date(
    Date.UTC(date.getFullYear(), date.getMonth(), date.getDate())
  );
  const n = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - n);
  const y = d.getUTCFullYear();
  const start = new Date(Date.UTC(y, 0, 1));
  return Math.ceil(((d.getTime() - start.getTime()) / 86400000 + 1) / 7);
}
const weekNumber = computed(() =>
  data.value?.week_start ? isoWeek(dayjs(data.value.week_start).toDate()) : 0
);

const weekDays = computed(() => data.value?.days ?? []);
// 英文星期 → 中文
function weekdayCN(en: string): string {
  return WEEKDAY_CN[en] || en;
}

const branches = computed(() => data.value?.branches ?? []);

const weekRangeText = computed(() => {
  const ws = data.value?.week_start;
  if (!ws) return "";
  const s = dayjs(ws);
  return `${s.format("MM月DD日")} - ${s.add(6, "day").format("MM月DD日")}`;
});

// 本月周列表：取本月第一个严格落在本月的周一作为第1周，逐周校验所属月
const monthWeeks = computed(() => {
  const now = dayjs();
  const startOfMonth = now.startOf("month");
  // 本月第一个周一（严格 ≥ 本月1号）
  const first =
    startOfMonth.day() === 0 ? startOfMonth.add(1, "day") : startOfMonth.day(1);
  const firstMonday =
    first.month() === startOfMonth.month() ? first : first.add(7, "day");
  const result: Array<{ value: string; label: string }> = [];
  for (let i = 0; i < 4; i++) {
    const monday = firstMonday.add(i * 7, "day");
    if (monday.month() !== startOfMonth.month()) break;
    result.push({
      value: monday.format("YYYY-MM-DD"),
      label: `第${i + 1}周（${monday.format("MM.DD")} - ${monday
        .add(6, "day")
        .format("MM.DD")}）`
    });
  }
  return result;
});

// 分支配色：固定色板；按 branch_id 稳定取色
const BRANCH_PALETTE = [
  "#3b82f6",
  "#8b5cf6",
  "#f59e0b",
  "#10b981",
  "#ef4444",
  "#06b6d4"
];
// 分支配色映射：一次计算，避免模板内重复 O(n) 查找
const branchColorMap = computed(() => {
  const map = new Map<number, string>();
  branches.value.forEach((b, idx) => {
    map.set(b.branch_id, BRANCH_PALETTE[(idx + 1) % BRANCH_PALETTE.length]);
  });
  return map;
});
function branchColor(branchId: number) {
  return branchColorMap.value.get(branchId) || BRANCH_PALETTE[0];
}

// 策略预分组：按 branch_id 过滤 + build_start_time 升序，避免 v-for 内重复计算
const strategyMap = computed(() => {
  const map = new Map<number, WeeklyStrategy[]>();
  for (const s of data.value?.strategies ?? []) {
    const list = map.get(s.branch_id);
    if (list) list.push(s);
    else map.set(s.branch_id, [s]);
  }
  for (const list of map.values()) {
    list.sort((a, c) => a.build_start_time.localeCompare(c.build_start_time));
  }
  return map;
});

// 详情抽屉
const drawerVisible = ref(false);
const selectedStrategy = ref<WeeklyStrategy | null>(null);
const selectedBranchName = ref("");
function selectStrategy(s: WeeklyStrategy, bname: string) {
  selectedStrategy.value = s;
  selectedBranchName.value = bname;
  drawerVisible.value = true;
}

async function load() {
  const cur = ++seq;
  loading.value = true;
  data.value = null; // 切换查询时清空旧数据，配合 v-loading 遮罩避免感知跳变
  try {
    const d = await getWeekly({
      week_start: selectedWeek.value || undefined,
      version_id: versionId.value
    });
    if (cur !== seq) return; // 过期响应丢弃
    data.value = d;
    if (!selectedWeek.value && d) selectedWeek.value = d.week_start;
  } catch (e) {
    if (cur !== seq) return;
    console.error("周视图加载失败", e);
    ElMessage.error("周视图数据加载失败");
  } finally {
    if (cur === seq) loading.value = false;
  }
}
onMounted(load);
</script>

<template>
  <div class="weekly-page">
    <!-- 第一行：周信息 + 本月周列表 + 版本选择 + 查询 -->
    <div class="row-card row-1">
      <div class="week-info">
        <span v-if="weekNumber > 0" class="week-title">
          今年第 <b>{{ weekNumber }}</b> 周，{{ weekRangeText }}
        </span>
        <span v-else class="week-title weekday-placeholder">周视图</span>
      </div>
      <div class="row-1-controls">
        <el-select
          v-model="selectedWeek"
          placeholder="选择本周"
          clearable
          style="width: 220px"
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
          placeholder="全部版本"
          clearable
          style="width: 160px"
        >
          <el-option
            v-for="v in versionOptions"
            :key="v.version_id"
            :value="v.version_id"
            :label="v.version_name"
          />
        </el-select>
        <el-button type="primary" :loading="loading" @click="load">查询</el-button>
      </div>
    </div>

    <!-- 第二行：当前版本分支标签 -->
    <div class="row-card row-2">
      <span class="row-2-label">当前版本</span>
      <template v-if="currentVersionName">
        <el-tag
          v-for="b in branches"
          :key="b.branch_id"
          class="branch-tag"
          :style="{ '--tag-color': branchColor(b.branch_id) }"
          effect="light"
        >
          {{ currentVersionName }} / {{ b.branch_name }}
        </el-tag>
      </template>
      <span v-else class="row-2-empty">请选择版本查看分支</span>
    </div>

    <!-- 第三行：核心网格 -->
    <div class="row-card row-3" v-loading="loading">
      <div class="grid-head">
        <div class="grid-corner">分支 / 时间</div>
        <div v-for="d in weekDays" :key="d.date" class="grid-col-head">
          <div class="col-weekday">{{ weekdayCN(d.weekday) }}</div>
          <div class="col-date">{{ d.date.slice(5) }}</div>
        </div>
      </div>
      <div v-for="b in branches" :key="b.branch_id" class="grid-row">
        <div class="grid-branch">{{ b.branch_name }}</div>
        <div v-for="d in weekDays" :key="d.date" class="grid-cell">
          <div
            v-for="s in strategyMap.get(b.branch_id) ?? []"
            :key="s.strategy_id"
            class="strategy-chip"
            :style="{ background: branchColor(b.branch_id) }"
            @click="selectStrategy(s, b.branch_name)"
          >
            <span class="chip-name">{{ s.strategy_name }}</span>
            <span class="chip-time">{{ s.build_start_time }}</span>
          </div>
        </div>
      </div>
      <el-empty
        v-if="!loading && data && branches.length === 0"
        description="该版本暂无分支"
      />
    </div>

    <!-- 第四行：图例 -->
    <div class="row-card row-4">
      <span class="legend-label">图例</span>
      <span v-for="b in branches" :key="b.branch_id" class="legend-item">
        <i class="legend-dot" :style="{ background: branchColor(b.branch_id) }"></i>
        {{ b.branch_name }}
      </span>
      <span v-if="branches.length === 0" class="legend-empty">暂无分支</span>
    </div>

    <!-- 策略详情抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :title="selectedStrategy ? selectedStrategy.strategy_name : '策略详情'"
      size="400px"
    >
      <template v-if="selectedStrategy">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="策略名">
            {{ selectedStrategy.strategy_name }}
          </el-descriptions-item>
          <el-descriptions-item label="分支">
            {{ selectedBranchName }}
          </el-descriptions-item>
          <el-descriptions-item label="模板">
            {{ selectedStrategy.template_name }}
          </el-descriptions-item>
          <el-descriptions-item label="构建开始">
            {{ selectedStrategy.build_start_time }}
          </el-descriptions-item>
          <el-descriptions-item label="推送时间">
            {{ selectedStrategy.push_start_time || "结论后推导" }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.weekly-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.row-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 16px;
}

/* ---- 第一行 ---- */
.row-1 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.week-info {
  display: flex;
  align-items: center;
}
.week-title {
  font-size: 15px;
  color: #303133;
}
.week-title b {
  color: #3b82f6;
  font-size: 18px;
  margin: 0 2px;
}
.weekday-placeholder {
  color: #909399;
}
.row-1-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* ---- 第二行 ---- */
.row-2 {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.row-2-label {
  font-size: 13px;
  color: #909399;
  margin-right: 4px;
}
.branch-tag {
  border-color: var(--tag-color);
  color: var(--tag-color);
}
.row-2-empty {
  color: #909399;
  font-size: 13px;
}

/* ---- 第三行：网格 ---- */
.row-3 {
  position: relative;
  min-height: 160px;
  padding: 0;
  overflow-x: auto;
}
.grid-head {
  display: grid;
  grid-template-columns: 140px repeat(7, 1fr);
  border-bottom: 1px solid #e5e7eb;
  background: #fafafa;
}
.grid-corner {
  padding: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  border-right: 1px solid #e5e7eb;
}
.grid-col-head {
  padding: 10px;
  text-align: center;
  border-right: 1px solid #f0f0f0;
}
.grid-col-head:last-child {
  border-right: none;
}
.col-weekday {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.col-date {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}
.grid-row {
  display: grid;
  grid-template-columns: 140px repeat(7, 1fr);
}
.grid-row + .grid-row {
  border-top: 1px solid #f0f0f0;
}
.grid-branch {
  padding: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  background: #fafafa;
  border-right: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
}
.grid-cell {
  min-height: 64px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border-right: 1px solid #f0f0f0;
}
.grid-cell:last-child {
  border-right: none;
}
.strategy-chip {
  border-radius: 6px;
  color: #fff;
  padding: 4px 8px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  transition: opacity 0.2s;
}
.strategy-chip:hover {
  opacity: 0.85;
}
.chip-name {
  font-size: 12px;
  line-height: 1.3;
  word-break: break-all;
}
.chip-time {
  font-size: 11px;
  opacity: 0.9;
}

/* ---- 第四行：图例 ---- */
.row-4 {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.legend-label {
  font-size: 13px;
  color: #909399;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #303133;
}
.legend-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
}
.legend-empty {
  color: #909399;
  font-size: 13px;
}
</style>