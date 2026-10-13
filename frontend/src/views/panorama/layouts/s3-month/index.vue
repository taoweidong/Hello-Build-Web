<!-- S3 月历时段矩阵视图 /panorama/month -->
<!-- 抢占主战场 + 策略标记叠加；复用 slot-booking 既有月历组件（改造后支持非抢占事件标记） -->
<template>
  <div class="biz-page">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button
            circle
            aria-label="上一月"
            size="small"
            @click="shiftMonth(-1)"
          >
            <IconifyIconOffline :icon="ArrowLeft" class="nav-icon" />
          </el-button>
          <span class="month-title">{{ monthLabel }}</span>
          <el-button
            circle
            aria-label="下一月"
            size="small"
            @click="shiftMonth(1)"
          >
            <IconifyIconOffline :icon="ArrowRight" class="nav-icon" />
          </el-button>
          <el-button size="small" text type="primary" @click="goThisMonth"
            >本月</el-button
          >
        </div>
        <div class="toolbar-stats">
          <span>策略 {{ strategyCount }}</span>
          <el-divider direction="vertical" />
          <span>已抢占 {{ kpi.weekSlotOccupied }} 段</span>
          <el-divider direction="vertical" />
          <span class="stat-mine">我的 {{ kpi.mySlots }} 段</span>
          <el-divider direction="vertical" />
          <span>待审批 {{ kpi.pendingBorrow }}</span>
        </div>
        <div class="toolbar-right">
          <el-button
            size="small"
            :type="kpi.pendingBorrow ? 'warning' : 'default'"
            @click="actions.openApproval()"
          >
            待我审批{{ kpi.pendingBorrow ? `（${kpi.pendingBorrow}）` : "" }}
          </el-button>
        </div>
      </div>
      <PanoramaFilterBar
        :versions="versionOptions"
        :branches="branchOptions"
        :version-id="query.versionId"
        :branch-ids="query.branchIds ?? []"
        :scope="query.scope ?? 'all'"
        :loading="loading"
        @update:version-id="onVersionChange"
        @update:branch-ids="onBranchChange"
        @update:scope="onScopeChange"
        @open-my-bookings="actions.openMyBookings()"
        @refresh="refresh()"
      />
      <div class="legend">
        <span class="legend-item"><i class="dot dot-slot" />抢占时段</span>
        <span class="legend-item"><i class="dot dot-strategy" />策略任务</span>
        <span class="legend-item"><i class="dot dot-borrow" />待审借用</span>
        <span class="legend-item"><i class="dot dot-expired" />已过期</span>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-skeleton v-if="loading" :rows="7" animated />
      <el-empty v-else-if="!monthCells.length" description="本月暂无调度数据" />
      <div v-else class="month-grid">
        <div v-for="w in WEEKDAY_CN_MON" :key="w" class="grid-head">
          {{ w }}
        </div>
        <div
          v-for="cell in monthCells"
          :key="cell.date"
          class="grid-cell"
          :class="{ 'cell-out': !cell.inMonth, 'cell-today': cell.isToday }"
        >
          <div class="cell-date">
            {{ cell.dayOfMonth }}
            <span v-if="cell.isToday" class="today-tag">今天</span>
          </div>
          <div class="cell-body">
            <ScheduleEventCard
              v-for="e in cell.events.slice(0, 3)"
              :key="e.id"
              :event="e"
              :show-meta="false"
              @click="onEventClick"
            />
            <el-button
              v-if="cell.events.length > 3"
              text
              size="small"
              type="primary"
              @click="openDayDetail(cell.date)"
            >
              +{{ cell.events.length - 3 }} 更多
            </el-button>
          </div>
        </div>
      </div>
    </el-card>

    <ScheduleDialogs />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import dayjs from "dayjs";
import { ElMessage } from "element-plus";
import ArrowLeft from "~icons/ep/arrow-left";
import ArrowRight from "~icons/ep/arrow-right";
import { usePanoramaPage } from "../../usePanoramaPage";
import PanoramaFilterBar from "../../shared/PanoramaFilterBar.vue";
import ScheduleEventCard from "../../shared/ScheduleEventCard.vue";
import ScheduleDialogs from "../../shared/ScheduleDialogs.vue";
import { buildMonthCells } from "@/utils/slotCalendar";
import { WEEKDAY_CN_MON } from "@/utils/week";
import type { ScheduleEvent } from "../../types";

defineOptions({ name: "PanoramaMonthLayout" });

// 首屏即加载当前月全量：月历是「抢占主战场」，若沿用默认本周范围，
// 当月大部分单元格会空摆，用户会误判整月无数据（翻月时 syncMonth 才补齐）
const month = ref(dayjs().format("YYYY-MM"));

const {
  query,
  actions,
  loading,
  lastLoadedAt,
  days,
  events,
  byDay,
  kpi,
  versionOptions,
  branchOptions,
  templates,
  horizonDays,
  refresh
} = usePanoramaPage({
  dateFrom: dayjs(`${month.value}-01`).format("YYYY-MM-DD"),
  dateTo: dayjs(`${month.value}-01`).endOf("month").format("YYYY-MM-DD")
});
const monthLabel = computed(() =>
  dayjs(`${month.value}-01`).format("YYYY年M月")
);

const monthCells = computed(() => {
  const cells = buildMonthCells(month.value);
  return cells.map(c => ({
    ...c,
    isToday: c.date === dayjs().format("YYYY-MM-DD"),
    dayOfMonth: dayjs(c.date).format("D"),
    events: byDay.value[c.date] ?? []
  }));
});

const strategyCount = computed(
  () =>
    events.value.filter(e => e.source === "strategy" && e.kind === "build")
      .length
);

function syncMonth() {
  query.value = {
    ...query.value,
    dateFrom: dayjs(`${month.value}-01`).format("YYYY-MM-DD"),
    dateTo: dayjs(`${month.value}-01`).endOf("month").format("YYYY-MM-DD")
  };
}

function shiftMonth(delta: number) {
  month.value = dayjs(`${month.value}-01`)
    .add(delta, "month")
    .format("YYYY-MM");
  syncMonth();
}

function goThisMonth() {
  month.value = dayjs().format("YYYY-MM");
  syncMonth();
}

function onVersionChange(value: number | undefined) {
  query.value = { ...query.value, versionId: value, branchIds: [] };
}

function onBranchChange(value: number[]) {
  query.value = { ...query.value, branchIds: value };
}

function onScopeChange(value: "all" | "mine") {
  query.value = { ...query.value, scope: value };
}

/** 事件点击分发：抢占/释放走时段弹窗，策略走编辑或借用，借用走审批抽屉 */
async function onEventClick(event: ScheduleEvent) {
  if (event.past) {
    ElMessage.info("该日程已过期，仅可查看");
    return;
  }
  if (event.source === "slot") {
    if (event.permissions.canOccupy) actions.openOccupy(event);
    else actions.openDetail(event);
    return;
  }
  if (event.source === "borrow") {
    // 审批人进抽屉批；申请人进抽屉撤回（P2-R1）
    if (event.permissions.canApprove || event.permissions.canCancel)
      actions.openApproval();
    else ElMessage.info("该借用申请待审批中");
    return;
  }
  if (event.permissions.canEdit) await actions.openEdit(event);
  else await actions.openBorrow(event);
}

function openDayDetail(date: string) {
  ElMessage.info(`${date} 当日共 ${byDay.value[date]?.length ?? 0} 项调度`);
}
</script>

<style scoped lang="scss">
.toolbar-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
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

.nav-icon {
  width: 14px;
  height: 14px;
}

.month-title {
  min-width: 96px;
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

    &.dot-slot {
      background: var(--el-color-success);
    }

    &.dot-strategy {
      background: var(--el-color-primary);
    }

    &.dot-borrow {
      background: var(--el-color-warning);
    }

    &.dot-expired {
      background: var(--el-fill-color);
    }
  }
}

.month-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
  min-width: 900px;
}

.grid-head {
  padding: 6px 0;
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.grid-cell {
  min-height: 96px;
  padding: 6px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;

  &.cell-out {
    background: var(--el-fill-color-light);
  }

  &.cell-today {
    border-color: var(--el-color-primary);
  }
}

.cell-date {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  gap: 4px;

  .today-tag {
    font-size: 11px;
    font-weight: 400;
    color: var(--el-color-primary);
    border: 1px solid var(--el-color-primary);
    border-radius: 4px;
    padding: 0 4px;
  }
}

.cell-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
