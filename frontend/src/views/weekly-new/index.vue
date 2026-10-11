<template>
  <div class="weekly-new">
    <!-- 工具栏 -->
    <el-card shadow="never" class="toolbar-card">
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
            <span>本周任务 {{ stats.tasks }}</span>
            <el-divider direction="vertical" />
            <span>已占 {{ stats.occupied }} 段</span>
            <el-divider direction="vertical" />
            <span class="stat-mine">我的 {{ stats.mine }} 段</span>
          </div>
          <el-button size="small" @click="drawerVisible = true"
            >我的抢占</el-button
          >
        </div>
      </div>
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
        <el-divider direction="vertical" />
        <span class="legend-item"><i class="dot dot-available" />空闲</span>
        <span class="legend-item"><i class="dot dot-mine" />我的</span>
        <span class="legend-item"><i class="dot dot-locked" />已抢占</span>
      </div>
    </el-card>

    <!-- 周视图网格 -->
    <el-card shadow="never" class="grid-card">
      <div v-loading="loading" class="grid-wrap">
        <el-empty v-if="!loading && !weekly" description="暂无数据" />
        <el-empty
          v-else-if="!loading && branches.length === 0"
          description="该版本暂无分支，无法排布任务"
        />
        <template v-else>
          <div class="grid-title">
            {{ currentVersionName }} · {{ weekRangeText }} 任务排布与时段抢占
            <span class="grid-sub"
              >（时间轴仅展示有排布的时段，按时间顺序排列）</span
            >
          </div>
          <HourGrid
            :days="weekDays"
            :rows="hourRows"
            :today="today"
            @slot-click="onSlotClick"
          />
        </template>
      </div>
    </el-card>

    <!-- 抢占弹窗（复用时段抢占） -->
    <BookingDialog
      v-model="bookingVisible"
      :date="bookingDate"
      :template="bookingTemplate"
      :horizon-end="horizonEnd"
      @booked="onBooked"
    />
    <!-- 时段详情（复用时段抢占） -->
    <SlotDetailDialog
      v-model="detailVisible"
      :date="detailDate"
      :entry="detailEntry"
      :template="detailTemplate"
      @released="onReleased"
    />
    <!-- 我的抢占抽屉（复用时段抢占） -->
    <MyBookingsDrawer v-model="drawerVisible" @changed="loadCalendars" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import dayjs from "dayjs";
import ArrowLeft from "~icons/ep/arrow-left";
import ArrowRight from "~icons/ep/arrow-right";
import { getWeekly } from "@/api/weekly";
import type { WeeklyData } from "@/api/types";
import { useBranchColors } from "@/composables/useBranchColors";
import {
  getSlotCalendar,
  type CalendarDayCell,
  type SlotCalendarResponse,
  type SlotTemplateItem
} from "@/api/slotBooking";
import BookingDialog from "@/views/slot-booking/components/BookingDialog.vue";
import SlotDetailDialog from "@/views/slot-booking/components/SlotDetailDialog.vue";
import MyBookingsDrawer from "@/views/slot-booking/components/MyBookingsDrawer.vue";
import HourGrid, {
  type HourSlotItem,
  type HourTaskItem
} from "./components/HourGrid.vue";

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

// ---- 周视图数据源（版本/分支/策略，与原周视图一致）----
const weekly = ref<WeeklyData | null>(null);
const weeklyLoading = ref(false);
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
const currentVersionName = computed(() => {
  const v = versionOptions.value.find(x => x.version_id === versionId.value);
  return v?.version_name ?? "";
});
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

/** 首屏是否已完成首次 versionId 选定：用于避免初始化阶段的重复请求 */
const initializing = ref(true);

async function loadWeekly() {
  weeklyLoading.value = true;
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
    weeklyLoading.value = false;
  }
}

// ---- 抢占状态数据源：周可能跨月，按涉及月份合并拉取 ----
const templates = ref<SlotTemplateItem[]>([]);
const horizonDays = ref(60);
const entriesByDate = ref<Map<string, Map<number, CalendarDayCell>>>(new Map());
const calendarLoading = ref(false);

async function loadCalendars() {
  calendarLoading.value = true;
  try {
    const months = [...new Set(weekDays.value.map(d => d.date.slice(0, 7)))];
    const responses = await Promise.all(months.map(m => getSlotCalendar(m)));
    const merged: Map<string, Map<number, CalendarDayCell>> = new Map();
    let tpl: SlotTemplateItem[] = [];
    for (const resp of responses as SlotCalendarResponse[]) {
      horizonDays.value = resp.horizon_days;
      if (!tpl.length) tpl = resp.templates;
      for (const [dateKey, entries] of Object.entries(resp.days)) {
        const map = new Map<number, CalendarDayCell>();
        for (const e of entries) map.set(e.template_id, e);
        merged.set(dateKey, map);
      }
    }
    templates.value = tpl;
    entriesByDate.value = merged;
  } catch {
    // 拦截器已提示
  } finally {
    calendarLoading.value = false;
  }
}

const loading = computed(() => weeklyLoading.value || calendarLoading.value);
const horizonEnd = computed(() =>
  dayjs().add(horizonDays.value, "day").format("YYYY-MM-DD")
);

function hourOf(hhmm: string) {
  return Number(hhmm.slice(0, 2));
}

/** 模板是否覆盖小时 h（模板强制同日 start<end） */
function coversHour(t: SlotTemplateItem, h: number) {
  return hourOf(t.start_time) <= h && h < hourOf(t.end_time);
}

/** 任务芯片（策略每日循环排布，7 天一致；按小时归类） */
function tasksAtHour(h: number): HourTaskItem[] {
  const tasks: HourTaskItem[] = [];
  for (const s of strategies.value) {
    if (hourOf(s.build_start_time) === h) {
      tasks.push({
        key: `b-${s.strategy_id}`,
        kind: "build",
        stageLabel: "构建",
        name: s.strategy_name,
        time: s.build_start_time,
        title: `构建 · ${s.strategy_name} · ${s.branch_name} · ${s.build_start_time}`,
        color: branchColor(s.branch_id)
      });
    }
    if (s.push_start_time && hourOf(s.push_start_time) === h) {
      tasks.push({
        key: `p-${s.strategy_id}`,
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

/** 仅保留有内容的小时行：任务芯片或任意一天的抢占条目 */
const hourRows = computed(() => {
  const rows: {
    hour: number;
    cells: { date: string; tasks: HourTaskItem[]; slots: HourSlotItem[] }[];
  }[] = [];
  for (let h = 0; h < 24; h++) {
    const tasks = tasksAtHour(h);
    const cells = weekDays.value.map(d => {
      const slots: HourSlotItem[] = [];
      const dayEntries = entriesByDate.value.get(d.date);
      for (const t of templates.value) {
        if (!coversHour(t, h)) continue;
        const entry = dayEntries?.get(t.id);
        if (!entry) continue;
        slots.push({ entry, template: t });
      }
      return { date: d.date, tasks, slots };
    });
    const hasContent = tasks.length > 0 || cells.some(c => c.slots.length > 0);
    if (hasContent) rows.push({ hour: h, cells });
  }
  return rows;
});

const stats = computed(() => {
  let occupied = 0;
  let mine = 0;
  for (const d of weekDays.value) {
    for (const e of entriesByDate.value.get(d.date)?.values() ?? []) {
      if (e.status === "reserved") {
        occupied += 1;
        if (e.booking?.is_mine) mine += 1;
      }
    }
  }
  return { tasks: strategies.value.length, occupied, mine };
});

// ---- 数据加载联动 ----
// 日历拉取依赖 weekDays（来自 weekly 响应），必须先等周数据返回
async function reloadAll() {
  await loadWeekly();
  await loadCalendars();
}

watch(weekStart, () => {
  selectedWeek.value = weekStart.value;
  reloadAll();
});
watch(versionId, value => {
  // 首屏由 reloadAll 负责串联加载；此处跳过，避免初始化二次请求
  if (!value || initializing.value) return;
  loadWeekly();
});

onMounted(async () => {
  try {
    await reloadAll();
  } finally {
    initializing.value = false;
  }
});

// ---- 抢占交互（与时段抢占页同款，作用到具体日期）----
const bookingVisible = ref(false);
const bookingDate = ref(today);
const bookingTemplate = ref<SlotTemplateItem | null>(null);

const detailVisible = ref(false);
const detailDate = ref(today);
const detailEntry = ref<CalendarDayCell | null>(null);
const detailTemplate = ref<SlotTemplateItem | null>(null);

const drawerVisible = ref(false);

function onSlotClick(date: string, entry: CalendarDayCell) {
  if (date < today) {
    ElMessage.info("该日期已过期，不可操作");
    return;
  }
  const template = templates.value.find(t => t.id === entry.template_id);
  if (!template) return;
  if (entry.status === "reserved") {
    detailDate.value = date;
    detailEntry.value = entry;
    detailTemplate.value = template;
    detailVisible.value = true;
    return;
  }
  if (date > horizonEnd.value) {
    ElMessage.warning(`超出可抢占窗口（最多提前 ${horizonDays.value} 天）`);
    return;
  }
  bookingDate.value = date;
  bookingTemplate.value = template;
  bookingVisible.value = true;
}

async function onBooked() {
  bookingVisible.value = false;
  ElMessage.success("抢占成功");
  await loadCalendars();
}

async function onReleased() {
  detailVisible.value = false;
  ElMessage.success("已释放");
  await loadCalendars();
}

reloadAll();
</script>

<style scoped lang="scss">
.weekly-new {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
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

  .stat-mine {
    color: var(--el-color-primary);
  }
}

.legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
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

  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;

    &.dot-available {
      background: var(--el-color-success-light-7);
      border: 1px solid var(--el-color-success);
    }

    &.dot-mine {
      background: var(--el-color-primary);
    }

    &.dot-locked {
      background: var(--el-fill-color);
      border: 1px solid var(--el-border-color);
    }
  }
}

.grid-wrap {
  overflow-x: auto;
}

.grid-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);

  .grid-sub {
    font-weight: 400;
    color: var(--el-text-color-placeholder);
  }
}
</style>
