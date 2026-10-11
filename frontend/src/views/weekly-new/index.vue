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
            @change="value => (weekStart = value || thisWeekMonday)"
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
            <span v-for="b in branches" :key="b.branch_id" class="legend-item">
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
        <HourGrid
          v-else
          :days="weekDays"
          :rows="timeRows"
          :today="today"
          :editable="canEdit"
          @task-click="openEditDialog"
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
  </div>
</template>

<script setup lang="ts">
// 版本策略全景(New)：以「本周 7 天为列、任务时间点为行」展示所选版本的策略排布全景
// 外部人员只读查看；内部维护人员（admin / 绑定版本的 pm）可点击任务芯片修改时间与信息
// 数据与周视图同源（GET /api/weekly），策略为每日循环，任务芯片 7 天一致
import { computed, onMounted, ref, watch } from "vue";
import dayjs from "dayjs";
import ArrowLeft from "~icons/ep/arrow-left";
import ArrowRight from "~icons/ep/arrow-right";
import { getWeekly } from "@/api/weekly";
import { getStrategies } from "@/api/strategy";
import type { WeeklyData, StrategyItem } from "@/api/types";
import { canEditPanorama, getCurrentUser } from "@/utils/business";
import { useBranchColors } from "@/composables/useBranchColors";
import HourGrid, { type HourTaskItem } from "./components/HourGrid.vue";
import StrategyEditDialog from "./components/StrategyEditDialog.vue";

defineOptions({ name: "WeeklyNewIndex" });

const today = dayjs().format("YYYY-MM-DD");
const thisWeekMonday = dayjs(today)
  .subtract((dayjs(today).day() + 6) % 7, "day")
  .format("YYYY-MM-DD");

// ---- 周选择 ----
const weekStart = ref(thisWeekMonday);
const isCurrentWeek = computed(() => weekStart.value === thisWeekMonday);
const weekEnd = computed(() =>
  weekDays.value.length
    ? weekDays.value[6].date
    : dayjs(weekStart.value).add(6, "day").format("YYYY-MM-DD")
);
const weekRangeText = computed(() => {
  const s = dayjs(weekStart.value);
  return `${s.format("YYYY年M月D日")} - ${dayjs(weekEnd.value).format("M月D日")}`;
});

function isoWeek(dateStr: string): number {
  const d = dayjs(dateStr).toDate();
  const n = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - n);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}
const weekNumber = computed(() =>
  weekStart.value ? isoWeek(weekStart.value) : 0
);

function shiftWeek(delta: number) {
  weekStart.value = dayjs(weekStart.value)
    .add(delta * 7, "day")
    .format("YYYY-MM-DD");
}

function goThisWeek() {
  weekStart.value = thisWeekMonday;
}

/** 本月周列表（与原周视图同规则：本月第一个周一为第 1 周） */
const monthWeeks = computed(() => {
  const now = dayjs();
  const startOfMonth = now.startOf("month");
  const first =
    startOfMonth.day() === 0 ? startOfMonth.add(1, "day") : startOfMonth.day(1);
  const firstMonday =
    first.month() === startOfMonth.month() ? first : first.add(7, "day");
  const result: Array<{ value: string; label: string }> = [];
  for (let i = 0; i < 6; i++) {
    const monday = firstMonday.add(i * 7, "day");
    if (monday.month() !== startOfMonth.month()) break;
    result.push({
      value: monday.format("YYYY-MM-DD"),
      label: `第${i + 1}周（${monday.format("MM.DD")} - ${monday.add(6, "day").format("MM.DD")}）`
    });
  }
  return result;
});

const selectedWeek = ref(thisWeekMonday);
watch(selectedWeek, value => {
  if (value && value !== weekStart.value) weekStart.value = value;
});

// ---- 数据源（版本/分支/策略，与原周视图一致）----
const weekly = ref<WeeklyData | null>(null);
const loading = ref(false);
const versionId = ref<number | undefined>(undefined);

// 后端返回英文星期（Monday…Sunday），与原周视图一致地转中文展示
const WEEKDAY_CN: Record<string, string> = {
  Monday: "周一",
  Tuesday: "周二",
  Wednesday: "周三",
  Thursday: "周四",
  Friday: "周五",
  Saturday: "周六",
  Sunday: "周日"
};

const versionOptions = computed(() => weekly.value?.versions ?? []);
const branches = computed(() => weekly.value?.branches ?? []);
const strategies = computed(() => weekly.value?.strategies ?? []);

// 分支配色：固定色板、按 branch_id 稳定取色（与 weekly 共用）
const { branchColor } = useBranchColors(branches);

/** 列头 7 天：星期转中文 */
const weekDays = computed(() =>
  (weekly.value?.days ?? []).map(d => ({
    date: d.date,
    weekday: WEEKDAY_CN[d.weekday] ?? d.weekday
  }))
);

/** 首次加载未选版本时，后端返回空分支/策略；自动回填第一个版本后由 watcher 二次拉取 */
async function loadWeekly() {
  loading.value = true;
  try {
    weekly.value = await getWeekly({
      week_start: weekStart.value,
      version_id: versionId.value
    });
    if (!versionId.value && weekly.value.versions.length) {
      versionId.value = weekly.value.versions[0].version_id;
    }
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false;
  }
}

/** 任务芯片（按精确时间点归类：构建/推送起始时间相等才落行） */
function tasksAtTime(t: string): HourTaskItem[] {
  const tasks: HourTaskItem[] = [];
  for (const s of strategies.value) {
    if (s.build_start_time === t) {
      tasks.push({
        key: `b-${s.strategy_id}`,
        strategyId: s.strategy_id,
        kind: "build",
        stageLabel: "构建",
        name: s.strategy_name,
        time: s.build_start_time,
        title: `构建 · ${s.strategy_name} · ${s.branch_name} · ${s.build_start_time}`,
        color: branchColor(s.branch_id)
      });
    }
    if (s.push_start_time && s.push_start_time === t) {
      tasks.push({
        key: `p-${s.strategy_id}`,
        strategyId: s.strategy_id,
        kind: "push",
        stageLabel: "推送",
        name: s.strategy_name,
        time: s.push_start_time,
        title: `推送 · ${s.strategy_name} · ${s.branch_name} · ${s.push_start_time}`,
        color: branchColor(s.branch_id)
      });
    }
  }
  return tasks;
}

/**
 * 时间点行：0:00~23:59 内仅渲染有任务的时间点，按时间升序（非线性铺满，无任务时段省略）。
 * 策略当前为每日循环，7 天共享同一组任务；结构按天独立，兼容将来每天时间点存在差异的情况。
 */
const timeRows = computed(() => {
  const times = new Set<string>();
  for (const s of strategies.value) {
    times.add(s.build_start_time);
    if (s.push_start_time) times.add(s.push_start_time);
  }
  return [...times].sort().map(t => ({
    time: t,
    cells: weekDays.value.map(d => ({ date: d.date, tasks: tasksAtTime(t) }))
  }));
});

const stats = computed(() => ({
  tasks: strategies.value.length,
  branches: branches.value.length
}));

// ---- 编辑能力：外部人员只读，内部维护人员（admin / 绑定版本的 pm）可修改任意时间与信息 ----
const currentUser = getCurrentUser();
const canEdit = computed(() =>
  canEditPanorama(
    currentUser?.role,
    currentUser?.bound_version_id,
    versionId.value
  )
);

// 策略详情缓存（芯片点击时按需拉取 /strategies；weekly 契约不含 template_id/enabled）
const strategyDetailList = ref<StrategyItem[] | null>(null);
const editVisible = ref(false);
const editStrategy = ref<StrategyItem | null>(null);

async function openEditDialog(task: HourTaskItem) {
  if (!canEdit.value || !versionId.value) return;
  if (!strategyDetailList.value) {
    try {
      strategyDetailList.value = await getStrategies({
        version_id: versionId.value
      });
    } catch {
      return; // 拦截器已提示
    }
  }
  const detail =
    strategyDetailList.value.find(x => x.id === task.strategyId) ?? null;
  if (!detail) return;
  editStrategy.value = detail;
  editVisible.value = true;
}

function onStrategySaved() {
  // 保存后详情缓存与周数据都需刷新（时间/启用状态可能变化）
  strategyDetailList.value = null;
  loadWeekly();
}

watch(weekStart, () => {
  selectedWeek.value = weekStart.value;
  loadWeekly();
});
watch(versionId, value => {
  // 版本变化（含首屏自动回填）都重新拉取，保证拿到该版本的分支与策略
  strategyDetailList.value = null;
  if (value) loadWeekly();
});

onMounted(() => {
  loadWeekly();
});
</script>

<style scoped lang="scss">
.weekly-new {
  display: flex;
  flex-direction: column;
  /* 视口高度扣除：顶部导航+页签 81px、内容区上下边距 48px、页脚约 23px */
  height: calc(100vh - 152px);
  min-height: 520px;
}

.main-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;

  :deep(.el-card__body) {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: 12px 16px;
  }
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.week-title {
  min-width: 240px;
  text-align: center;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);

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
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);

  .legend-item {
    display: inline-flex;
    align-items: center;
    gap: 4px;
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
  flex: 1;
  min-height: 0;
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  overflow: auto;
}
</style>
