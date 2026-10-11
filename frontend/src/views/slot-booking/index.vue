<template>
  <div class="slot-booking">
    <!-- 工具栏 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button
            class="nav-btn"
            circle
            aria-label="上一月"
            @click="shiftMonth(-1)"
          >
            <IconifyIconOffline
              :icon="ArrowLeft"
              style="width: 14px; height: 14px"
            />
          </el-button>
          <span class="month-title">{{ monthLabel }}</span>
          <el-button
            class="nav-btn"
            circle
            aria-label="下一月"
            @click="shiftMonth(1)"
          >
            <IconifyIconOffline
              :icon="ArrowRight"
              style="width: 14px; height: 14px"
            />
          </el-button>
          <el-button size="small" text type="primary" @click="goToday"
            >今天</el-button
          >
        </div>
        <div class="toolbar-stats">
          <span>本月 {{ stats.total }} 段</span>
          <el-divider direction="vertical" />
          <span>已占 {{ stats.occupied }} 段</span>
          <el-divider direction="vertical" />
          <span class="stat-mine">我的 {{ stats.mine }} 段</span>
        </div>
        <div class="toolbar-right">
          <el-button size="small" @click="drawerVisible = true"
            >我的抢占</el-button
          >
        </div>
      </div>
      <div class="legend">
        <span class="legend-item"><i class="dot dot-available" />空闲</span>
        <span class="legend-item"><i class="dot dot-mine" />我的</span>
        <span class="legend-item"><i class="dot dot-locked" />已抢占</span>
        <span class="legend-item"><i class="dot dot-expired" />已过期</span>
        <span class="legend-item"><i class="dot dot-na" />非适用日</span>
      </div>
    </el-card>

    <!-- 月历主体 -->
    <el-card shadow="never" class="calendar-card">
      <el-skeleton v-if="loading" :rows="7" animated />
      <el-result
        v-else-if="loadError"
        icon="error"
        title="加载失败"
        :sub-title="loadError"
      >
        <template #extra>
          <el-button type="primary" @click="load">重试</el-button>
        </template>
      </el-result>
      <el-empty
        v-else-if="!calendar || calendar.templates.length === 0"
        description="暂无可抢占时段"
      >
        <el-button
          v-if="isAdmin"
          type="primary"
          @click="router.push('/slot-config')"
        >
          去配置时段
        </el-button>
        <span v-else class="empty-tip">请联系管理员在「时段配置」中添加</span>
      </el-empty>
      <MonthGrid
        v-else
        :cells="cells"
        :days="calendar.days"
        :templates="templateMap"
        :today="today"
        :horizon-end="horizonEnd"
        @chip-click="onChipClick"
        @more-click="openDayDetail"
      />
    </el-card>

    <!-- 抢占弹窗 -->
    <BookingDialog
      v-model="bookingVisible"
      :date="bookingDate"
      :template="bookingTemplate"
      :horizon-end="horizonEnd"
      @booked="onBooked"
    />
    <!-- 时段详情（我的 → 可释放 / 他人 → 只读） -->
    <SlotDetailDialog
      v-model="detailVisible"
      :date="detailDate"
      :entry="detailEntry"
      :template="detailTemplate"
      @released="onReleased"
    />
    <!-- 单日全时段详情（+N 展开） -->
    <DayDetailDialog
      v-model="dayDetailVisible"
      :date="dayDetailDate"
      :entries="dayDetailEntries"
      :templates="templateMap"
      :today="today"
      :horizon-end="horizonEnd"
      @chip-click="
        (entry: CalendarDayCell) => onChipClick(dayDetailDate, entry)
      "
    />
    <!-- 我的抢占抽屉 -->
    <MyBookingsDrawer v-model="drawerVisible" @changed="load" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import dayjs from "dayjs";
import { ElMessage } from "element-plus";
import ArrowLeft from "~icons/ep/arrow-left";
import ArrowRight from "~icons/ep/arrow-right";
import {
  getSlotCalendar,
  type CalendarDayCell,
  type SlotCalendarResponse,
  type SlotTemplateItem
} from "@/api/slotBooking";
import MonthGrid from "./components/MonthGrid.vue";
import BookingDialog from "./components/BookingDialog.vue";
import SlotDetailDialog from "./components/SlotDetailDialog.vue";
import DayDetailDialog from "./components/DayDetailDialog.vue";
import MyBookingsDrawer from "./components/MyBookingsDrawer.vue";
import { getCurrentUser } from "@/utils/business";

defineOptions({ name: "SlotBookingIndex" });

const route = useRoute();
const router = useRouter();
// 业务身份统一取 localStorage 快照（与其余业务页一致，避免 pinia/快照双源）
const isAdmin = computed(() => getCurrentUser()?.role === "admin");

const loading = ref(false);
const loadError = ref("");
const calendar = ref<SlotCalendarResponse | null>(null);

const month = ref<string>(
  typeof route.query.month === "string"
    ? route.query.month
    : dayjs().format("YYYY-MM")
);
const today = dayjs().format("YYYY-MM-DD");

const monthLabel = computed(() => {
  const d = dayjs(`${month.value}-01`);
  return d.isValid() ? d.format("YYYY年M月") : month.value;
});
const horizonEnd = computed(() =>
  dayjs()
    .add(calendar.value?.horizon_days ?? 60, "day")
    .format("YYYY-MM-DD")
);
const templateMap = computed<Record<number, SlotTemplateItem>>(() => {
  const map: Record<number, SlotTemplateItem> = {};
  for (const t of calendar.value?.templates ?? []) map[t.id] = t;
  return map;
});

/** 月历 42 格（周一开头，含上下月补位） */
const cells = computed(() => {
  const first = dayjs(`${month.value}-01`);
  if (!first.isValid()) return [];
  const offset = (first.day() + 6) % 7; // day(): 0=周日 → 转周一开头
  const start = first.subtract(offset, "day");
  const list: { date: string; inMonth: boolean }[] = [];
  for (let i = 0; i < 42; i++) {
    const d = start.add(i, "day");
    list.push({
      date: d.format("YYYY-MM-DD"),
      inMonth: d.format("YYYY-MM") === month.value
    });
  }
  return list;
});

/** 工具栏统计：本月展示总段数 / 已占 / 我的 */
const stats = computed(() => {
  let total = 0;
  let occupied = 0;
  let mine = 0;
  for (const entries of Object.values(calendar.value?.days ?? {})) {
    for (const e of entries) {
      total += 1;
      if (e.status === "reserved") {
        occupied += 1;
        if (e.booking?.is_mine) mine += 1;
      }
    }
  }
  return { total, occupied, mine };
});

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    calendar.value = await getSlotCalendar(month.value);
  } catch (e: any) {
    loadError.value = e?.message || "请求失败";
  } finally {
    loading.value = false;
  }
}

function setMonth(value: string) {
  if (value === month.value) return;
  month.value = value;
  router.replace({ query: { ...route.query, month: value } });
  // month.value 已同步，下方 watcher 的 value !== month.value 不会命中，
  // 必须显式拉取（旧实现翻页后日历 42 格全空）；watcher 仅服务浏览器前进/后退
  load();
}

function shiftMonth(delta: number) {
  setMonth(dayjs(`${month.value}-01`).add(delta, "month").format("YYYY-MM"));
}

function goToday() {
  setMonth(dayjs().format("YYYY-MM"));
}

watch(
  () => route.query.month,
  value => {
    if (typeof value === "string" && value !== month.value) {
      month.value = value;
      load();
    }
  }
);

// ---- 芯片交互 ----
const bookingVisible = ref(false);
const bookingDate = ref("");
const bookingTemplate = ref<SlotTemplateItem | null>(null);

const detailVisible = ref(false);
const detailDate = ref("");
const detailEntry = ref<CalendarDayCell | null>(null);
const detailTemplate = ref<SlotTemplateItem | null>(null);

const dayDetailVisible = ref(false);
const dayDetailDate = ref("");
const dayDetailEntries = ref<CalendarDayCell[]>([]);

const drawerVisible = ref(false);

function onChipClick(dateStr: string, entry: CalendarDayCell) {
  if (dateStr < today) {
    ElMessage.info("该日期已过期，不可操作");
    return;
  }
  const template = templateMap.value[entry.template_id];
  if (!template) return;
  if (entry.status === "reserved") {
    detailDate.value = dateStr;
    detailEntry.value = entry;
    detailTemplate.value = template;
    detailVisible.value = true;
    return;
  }
  if (dateStr > horizonEnd.value) {
    ElMessage.warning(
      `超出可抢占窗口（最多提前 ${calendar.value?.horizon_days ?? 60} 天）`
    );
    return;
  }
  bookingDate.value = dateStr;
  bookingTemplate.value = template;
  bookingVisible.value = true;
}

function openDayDetail(dateStr: string, entries: CalendarDayCell[]) {
  dayDetailDate.value = dateStr;
  dayDetailEntries.value = entries;
  dayDetailVisible.value = true;
}

async function onBooked() {
  bookingVisible.value = false;
  ElMessage.success("抢占成功");
  await load();
}

async function onReleased() {
  detailVisible.value = false;
  ElMessage.success("已释放");
  await load();
}

load();
</script>

<style scoped lang="scss">
.slot-booking {
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

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.month-title {
  min-width: 108px;
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
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
  gap: 16px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);

  .legend-item {
    display: inline-flex;
    align-items: center;
    gap: 4px;
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

    &.dot-expired {
      background: var(--el-fill-color-light);
    }

    &.dot-na {
      background: transparent;
      border: 1px dashed var(--el-border-color-lighter);
    }
  }
}

.empty-tip {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
