<template>
  <div class="weekly-new">
    <!-- 工具栏 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button
            class="nav-btn"
            circle
            aria-label="前一天"
            @click="shiftDate(-1)"
          >
            <IconifyIconOffline
              :icon="ArrowLeft"
              style="width: 14px; height: 14px"
            />
          </el-button>
          <span class="date-title">
            {{ dateLabel }}
            <el-tag
              size="small"
              :type="isToday ? 'primary' : 'info'"
              effect="plain"
              class="weekday-tag"
            >
              {{ weekdayLabel }}
            </el-tag>
          </span>
          <el-button
            class="nav-btn"
            circle
            aria-label="后一天"
            @click="shiftDate(1)"
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
            :disabled="isToday"
            @click="goToday"
          >
            今天
          </el-button>
          <el-select
            v-model="versionId"
            filterable
            size="small"
            placeholder="选择版本"
            style="width: 150px; margin-left: 8px"
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
            <span>本日任务 {{ stats.tasks }}</span>
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

    <!-- 无模板提示 -->
    <el-alert
      v-if="!calendarLoading && calendar && calendar.templates.length === 0"
      title="暂无可抢占时段模板，请联系管理员在「时段配置」中添加"
      type="info"
      :closable="false"
      show-icon
    />

    <!-- 24 小时网格 -->
    <el-card shadow="never" class="grid-card">
      <div v-loading="loading">
        <el-empty v-if="!loading && !weekly" description="暂无数据" />
        <template v-else>
          <div class="grid-title">
            {{ currentVersionName }} · {{ date }} 任务排布与时段抢占（00:00 –
            24:00）
          </div>
          <HourGrid :rows="hourRows" :past="isPast" @slot-click="onSlotClick" />
        </template>
      </div>
    </el-card>

    <!-- 抢占弹窗（复用时段抢占） -->
    <BookingDialog
      v-model="bookingVisible"
      :date="date"
      :template="bookingTemplate"
      :horizon-end="horizonEnd"
      @booked="onBooked"
    />
    <!-- 时段详情（复用时段抢占） -->
    <SlotDetailDialog
      v-model="detailVisible"
      :date="date"
      :entry="detailEntry"
      :template="detailTemplate"
      @released="onReleased"
    />
    <!-- 我的抢占抽屉（复用时段抢占） -->
    <MyBookingsDrawer v-model="drawerVisible" @changed="loadCalendar" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import dayjs from "dayjs";
import ArrowLeft from "~icons/ep/arrow-left";
import ArrowRight from "~icons/ep/arrow-right";
import { getWeekly } from "@/api/weekly";
import type { WeeklyData } from "@/api/types";
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

const WEEKDAY_CN = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
// 分支配色与周视图保持一致
const BRANCH_PALETTE = [
  "#3b82f6",
  "#8b5cf6",
  "#f59e0b",
  "#10b981",
  "#ef4444",
  "#06b6d4"
];

const today = dayjs().format("YYYY-MM-DD");
const date = ref(today);
const isToday = computed(() => date.value === today);
const isPast = computed(() => date.value < today);
const dateLabel = computed(() => dayjs(date.value).format("YYYY年M月D日"));
const weekdayLabel = computed(() => WEEKDAY_CN[dayjs(date.value).day()]);

// ---- 周视图数据源（版本/分支/策略）----
const weekly = ref<WeeklyData | null>(null);
const weeklyLoading = ref(false);
const versionId = ref<number | undefined>(undefined);
const calendar = ref<SlotCalendarResponse | null>(null);
const calendarLoading = ref(false);

const versionOptions = computed(() => weekly.value?.versions ?? []);
const currentVersionName = computed(() => {
  const v = versionOptions.value.find(x => x.version_id === versionId.value);
  return v?.version_name ?? "";
});
const branches = computed(() => weekly.value?.branches ?? []);
const strategies = computed(() => weekly.value?.strategies ?? []);

const branchColorMap = computed(() => {
  const map = new Map<number, string>();
  branches.value.forEach((b, idx) => {
    map.set(b.branch_id, BRANCH_PALETTE[(idx + 1) % BRANCH_PALETTE.length]);
  });
  return map;
});
function branchColor(branchId: number) {
  return branchColorMap.value.get(branchId) ?? BRANCH_PALETTE[0];
}

async function loadWeekly() {
  weeklyLoading.value = true;
  try {
    weekly.value = await getWeekly({
      version_id: versionId.value
    });
    // 后端未选版本时不返回策略：默认选中版本列表第一项
    if (!versionId.value && weekly.value.versions.length) {
      versionId.value = weekly.value.versions[0].version_id;
    }
  } catch {
    // 拦截器已提示
  } finally {
    weeklyLoading.value = false;
  }
}

// ---- 抢占状态数据源（与时段抢占页一致）----
async function loadCalendar() {
  calendarLoading.value = true;
  try {
    calendar.value = await getSlotCalendar(date.value.slice(0, 7));
  } catch {
    // 拦截器已提示
  } finally {
    calendarLoading.value = false;
  }
}

const loading = computed(() => weeklyLoading.value || calendarLoading.value);
const horizonEnd = computed(() =>
  dayjs()
    .add(calendar.value?.horizon_days ?? 60, "day")
    .format("YYYY-MM-DD")
);

/** 当日各模板状态（slot-calendar 仅返回适用模板条目） */
const dayEntries = computed<Map<number, CalendarDayCell>>(() => {
  const map = new Map<number, CalendarDayCell>();
  for (const e of calendar.value?.days[date.value] ?? []) {
    map.set(e.template_id, e);
  }
  return map;
});

function hourOf(hhmm: string) {
  return Number(hhmm.slice(0, 2));
}

/** 模板是否覆盖小时 h（模板强制同日 start<end） */
function coversHour(t: SlotTemplateItem, h: number) {
  return hourOf(t.start_time) <= h && h < hourOf(t.end_time);
}

/** 24 行小时网格数据：任务芯片 + 抢占芯片 */
const hourRows = computed(() => {
  const rows: { hour: number; tasks: HourTaskItem[]; slots: HourSlotItem[] }[] =
    [];
  const list = strategies.value;
  for (let h = 0; h < 24; h++) {
    const tasks: HourTaskItem[] = [];
    for (const s of list) {
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
    const slots: HourSlotItem[] = [];
    for (const t of calendar.value?.templates ?? []) {
      if (!coversHour(t, h)) continue;
      const entry = dayEntries.value.get(t.id);
      if (!entry) continue; // 该日不适用（weekdays/生效期）
      slots.push({ entry, template: t });
    }
    rows.push({ hour: h, tasks, slots });
  }
  return rows;
});

const stats = computed(() => {
  let occupied = 0;
  let mine = 0;
  for (const e of dayEntries.value.values()) {
    if (e.status === "reserved") {
      occupied += 1;
      if (e.booking?.is_mine) mine += 1;
    }
  }
  return { tasks: strategies.value.length, occupied, mine };
});

// ---- 日期导航 ----
function shiftDate(delta: number) {
  date.value = dayjs(date.value).add(delta, "day").format("YYYY-MM-DD");
}

function goToday() {
  date.value = today;
}

// 跨月切换日期时重拉月历
watch(
  () => date.value.slice(0, 7),
  () => loadCalendar()
);

// 版本切换重拉周视图数据
watch(versionId, value => {
  if (value) loadWeekly();
});

// ---- 抢占交互（与时段抢占页同款）----
const bookingVisible = ref(false);
const bookingTemplate = ref<SlotTemplateItem | null>(null);

const detailVisible = ref(false);
const detailEntry = ref<CalendarDayCell | null>(null);
const detailTemplate = ref<SlotTemplateItem | null>(null);

const drawerVisible = ref(false);

function onSlotClick(_hour: number, entry: CalendarDayCell) {
  if (isPast.value) {
    ElMessage.info("该日期已过期，不可操作");
    return;
  }
  const template = calendar.value?.templates.find(
    t => t.id === entry.template_id
  );
  if (!template) return;
  if (entry.status === "reserved") {
    detailEntry.value = entry;
    detailTemplate.value = template;
    detailVisible.value = true;
    return;
  }
  if (date.value > horizonEnd.value) {
    ElMessage.warning(
      `超出可抢占窗口（最多提前 ${calendar.value?.horizon_days ?? 60} 天）`
    );
    return;
  }
  bookingTemplate.value = template;
  bookingVisible.value = true;
}

async function onBooked() {
  bookingVisible.value = false;
  ElMessage.success("抢占成功");
  await loadCalendar();
}

async function onReleased() {
  detailVisible.value = false;
  ElMessage.success("已释放");
  await loadCalendar();
}

loadWeekly();
loadCalendar();
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

.date-title {
  min-width: 190px;
  text-align: center;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);

  .weekday-tag {
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

.grid-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}
</style>
