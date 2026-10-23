<!-- S3 月历时段矩阵视图 /panorama/month -->
<!-- 抢占主战场 + 策略标记叠加；月历 42 格复用 utils/slotCalendar.buildMonthCells 唯一实现 -->
<template>
  <div class="biz-page">
    <el-card shadow="never" class="biz-toolbar-card">
      <div class="biz-toolbar">
        <div class="biz-toolbar-left">
          <el-button
            circle
            aria-label="上一月"
            size="small"
            @click="shiftMonth(-1)"
          >
            <IconifyIconOffline :icon="ArrowLeft" class="biz-nav-icon" />
          </el-button>
          <span class="biz-range-title">{{ monthLabel }}</span>
          <el-button
            circle
            aria-label="下一月"
            size="small"
            @click="shiftMonth(1)"
          >
            <IconifyIconOffline :icon="ArrowRight" class="biz-nav-icon" />
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
        </div>
        <div class="biz-toolbar-right">
          <el-button
            size="small"
            :type="kpi.pendingBorrow ? 'warning' : 'default'"
            @click="actions.openApproval()"
          >
            待我审批{{ kpi.pendingBorrow ? `（${kpi.pendingBorrow}）` : "" }}
          </el-button>
          <!-- 图例并入工具条右组：原独占一行，纯为省一行高度 -->
          <div class="biz-legend">
            <span class="legend-item"><i class="dot dot-slot" />抢占时段</span>
            <span class="legend-item"
              ><i class="dot dot-strategy" />策略任务</span
            >
            <span class="legend-item"
              ><i class="dot dot-borrow" />待审借用</span
            >
            <span class="legend-item"><i class="dot dot-expired" />已过期</span>
          </div>
        </div>
      </div>
      <PanoramaFilterBar
        :versions="versionOptions"
        :branches="branchOptions"
        :version-id="query.versionId"
        :branch-ids="query.branchIds ?? []"
        :scope="query.scope ?? 'all'"
        :loading="loading"
        @update:version-id="setVersion"
        @update:branch-ids="setBranches"
        @update:scope="setScope"
        @open-my-bookings="actions.openMyBookings()"
        @refresh="refresh()"
      />
    </el-card>

    <el-card shadow="never" class="biz-content-card">
      <el-skeleton v-if="loading" :rows="7" animated />
      <el-empty v-else-if="!monthCells.length" description="本月暂无调度数据" />
      <div v-else class="biz-scroll-x">
        <div class="month-grid">
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
                @click="goTimeline(cell.date)"
              >
                +{{ cell.events.length - 3 }} 更多
              </el-button>
            </div>
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
import { useRouter } from "vue-router";
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
const router = useRouter();

const {
  query,
  actions,
  loading,
  events,
  byDay,
  kpi,
  versionOptions,
  branchOptions,
  refresh,
  // 查询变更器统一走装配总线（R4-F9：删除本文件逐字复制的处理器副本）
  setVersion,
  setBranches,
  setScope,
  setDateRange
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
  setDateRange(
    dayjs(`${month.value}-01`).format("YYYY-MM-DD"),
    dayjs(`${month.value}-01`).endOf("month").format("YYYY-MM-DD")
  );
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

/** 事件点击分发：抢占/释放走时段弹窗，策略走编辑或借用，借用走审批抽屉 */
async function onEventClick(event: ScheduleEvent) {
  // 抢占事件：可抢则进抢占弹窗，否则进详情——过期抢占放行详情（R6-F8，
  // 与 S4/S5 行内「详情」恒可用口径对齐，历史抢占可溯源）
  if (event.source === "slot") {
    if (event.permissions.canOccupy) actions.openOccupy(event);
    else actions.openDetail(event);
    return;
  }
  if (event.past) {
    ElMessage.info("该日程已过期，仅可查看");
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

/** 下钻当日时间轴（S5）：与 S1 热力格点击同一下钻口径，保持同一数据中枢 */
function goTimeline(date: string) {
  // 对象写法交给 router 序列化 query（R4-F13/F-L5：不再模板串手拼 URL）
  router.push({ path: "/panorama/timeline", query: { date } });
}
</script>

<style scoped lang="scss">
.toolbar-stats {
  font-size: 13px;
  color: var(--el-text-color-secondary);

  .stat-mine {
    color: var(--el-color-primary);
  }
}

/* 月历专属色点（容器 .biz-legend 与通用色点在 business.scss） */
.dot-strategy {
  background: var(--el-color-primary);
}

.dot-expired {
  background: var(--el-fill-color);
}

.month-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 4px;
  min-width: 900px;
}

.grid-head {
  padding: 4px 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
}

/* 日历格紧凑：高度由 96→76，芯片行内压薄，单日一屏可见密度提高 */
.grid-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-height: 76px;
  padding: 4px 5px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;

  :deep(.schedule-chip) {
    padding: 2px 6px;
    line-height: 14px;
  }

  &.cell-out {
    background: var(--el-fill-color-light);
  }

  &.cell-today {
    border-color: var(--el-color-primary);
  }
}

.cell-date {
  display: flex;
  gap: 4px;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);

  .today-tag {
    padding: 0 4px;
    font-size: 11px;
    font-weight: 400;
    color: var(--el-color-primary);
    border: 1px solid var(--el-color-primary);
    border-radius: 4px;
  }
}

.cell-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
