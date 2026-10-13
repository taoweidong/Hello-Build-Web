<!-- S1 调度大屏态势视图 /panorama/dashboard -->
<!-- 定位：值不值得点进去看。适用：每日巡检 / 投屏 / 值班快速发现异常 -->
<template>
  <div class="biz-page" :class="{ 'present-mode': presentMode }">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button
            circle
            aria-label="上一周"
            size="small"
            @click="shiftWeek(-1)"
          >
            <IconifyIconOffline :icon="ArrowLeft" class="nav-icon" />
          </el-button>
          <span class="range-title">{{ rangeText }}</span>
          <el-button
            circle
            aria-label="下一周"
            size="small"
            @click="shiftWeek(1)"
          >
            <IconifyIconOffline :icon="ArrowRight" class="nav-icon" />
          </el-button>
          <el-button size="small" text type="primary" @click="goThisWeek"
            >本周</el-button
          >
        </div>
        <div class="toolbar-right">
          <span class="tooltip-text">
            {{
              lastLoadedAt
                ? `更新于 ${formatTime(lastLoadedAt, "HH:mm:ss")}`
                : ""
            }}
          </span>
          <el-switch v-model="presentMode" size="small" />
          <span class="biz-sub">投屏模式</span>
        </div>
      </div>
      <!-- 投屏模式：隐藏筛选栏（大屏巡检场景只需「看」，避免误触筛选） -->
      <PanoramaFilterBar
        v-if="!presentMode"
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
    </el-card>

    <div class="biz-stat-grid">
      <div class="stat-item">
        <div class="stat-label">今日构建</div>
        <div class="stat-value">{{ kpi.todayBuild }}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">本周抢占</div>
        <div class="stat-value">
          {{ kpi.weekSlotOccupied }}<small>/{{ kpi.weekSlotTotal }}</small>
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-label">待我审批</div>
        <div class="stat-value" :class="{ 'stat-alert': pendingApproval }">
          {{ pendingApproval }}
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-label">我的有效抢占</div>
        <div class="stat-value">{{ myReservedSlots }}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">跨源冲突</div>
        <div class="stat-value" :class="{ 'stat-alert': kpi.conflictCount }">
          {{ kpi.conflictCount }}
        </div>
      </div>
    </div>

    <div class="dashboard-grid">
      <el-card shadow="never" class="panel">
        <template #header>
          <div class="biz-card-head">
            <span class="biz-card-title">本周负载热力（时刻 × 周一~周日）</span>
            <span class="biz-sub">占用率 {{ kpi.occupancyRate }}%</span>
          </div>
        </template>
        <div class="biz-scroll-x">
          <div class="heat-grid">
            <div class="heat-corner">时刻</div>
            <div v-for="d in days" :key="d.date" class="heat-head">
              {{ d.weekday }}
            </div>
            <template v-for="row in heatRows" :key="row.time">
              <div class="heat-time">{{ row.time }}</div>
              <div
                v-for="(count, idx) in row.counts"
                :key="idx"
                class="heat-cell"
                :class="{ 'heat-empty': count === 0 }"
                :style="{ opacity: count === 0 ? 0.35 : 1 }"
                :title="heatTitle(days[idx], row.time, count)"
                @click="goTimeline(days[idx]?.date)"
              >
                {{ count || "" }}
              </div>
            </template>
          </div>
        </div>
      </el-card>

      <div class="side-stack">
        <el-card shadow="never" class="panel">
          <template #header>
            <div class="biz-card-head">
              <span class="biz-card-title">异常告警</span>
            </div>
          </template>
          <p v-if="!conflicts.length" class="biz-tip">暂无跨源冲突。</p>
          <ul v-else class="alert-list">
            <li v-for="c in conflicts.slice(0, 8)" :key="c.id">
              <el-icon><WarningFilled /></el-icon>
              <span
                >{{ c.date }} {{ c.time }} {{ c.title }} 与已抢占时段重合</span
              >
            </li>
          </ul>
        </el-card>

        <el-card shadow="never" class="panel">
          <template #header>
            <div class="biz-card-head">
              <span class="biz-card-title">待办队列</span>
              <el-button
                size="small"
                type="primary"
                @click="actions.openApproval()"
                >去审批</el-button
              >
            </div>
          </template>
          <p v-if="!borrowFlows.length" class="biz-tip">暂无待审批借用。</p>
          <ul v-else class="todo-list">
            <li v-for="f in borrowFlows" :key="f.id">
              <span class="todo-title">{{ f.title }}</span>
              <span class="todo-actions">
                <el-button
                  v-if="f.permissions.canApprove"
                  size="small"
                  type="primary"
                  @click="actions.approve(f)"
                  >通过</el-button
                >
                <el-button
                  v-if="f.permissions.canApprove"
                  size="small"
                  type="danger"
                  plain
                  @click="actions.reject(f)"
                  >驳回</el-button
                >
                <el-button
                  v-if="f.permissions.canCancel"
                  size="small"
                  type="warning"
                  plain
                  @click="actions.cancelBorrow(f)"
                  >撤销</el-button
                >
              </span>
            </li>
          </ul>
        </el-card>
      </div>
    </div>

    <ScheduleDialogs />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import dayjs from "dayjs";
import { useRouter } from "vue-router";
import ArrowLeft from "~icons/ep/arrow-left";
import ArrowRight from "~icons/ep/arrow-right";
import WarningFilled from "~icons/ep/warning-filled";
import { usePanoramaPage } from "../../usePanoramaPage";
import PanoramaFilterBar from "../../shared/PanoramaFilterBar.vue";
import ScheduleDialogs from "../../shared/ScheduleDialogs.vue";
import {
  buildHeatmap,
  collectTimePoints,
  detectCrossSourceConflicts
} from "../../selectors";
import { formatTime } from "@/utils/business";

defineOptions({ name: "PanoramaDashboardLayout" });

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
  todos,
  refresh
} = usePanoramaPage();
const router = useRouter();

const rangeText = computed(
  () =>
    `${dayjs(query.value.dateFrom).format("M月D日")} - ${dayjs(
      query.value.dateTo
    ).format("M月D日")}`
);

const conflicts = computed(() => detectCrossSourceConflicts(events.value));
const borrowFlows = computed(() =>
  events.value.filter(e => e.source === "borrow")
);

/** 投屏模式：隐藏筛选栏 + 放大关键数值（仅信息密度差异，不改配色） */
const presentMode = ref(false);

// 待办计数优先取服务端聚合（跨筛选准确）；接口不可用时回退前端聚合（§6-Q6 降级口径）
const pendingApproval = computed(
  () => todos.value?.pending_approval ?? kpi.value.pendingBorrow
);
const myReservedSlots = computed(
  () => todos.value?.my_reserved_slots ?? kpi.value.mySlots
);

/** 时刻 × 星期 热力：仅取范围内真实出现过的时刻，避免 24 行空行 */
const heatRows = computed(() => {
  const points = collectTimePoints(events.value);
  return buildHeatmap(events.value, days.value, points.slice(0, 12));
});

function shiftWeek(delta: number) {
  const from = dayjs(query.value.dateFrom)
    .add(delta * 7, "day")
    .format("YYYY-MM-DD");
  query.value = {
    ...query.value,
    dateFrom: from,
    dateTo: dayjs(from).add(6, "day").format("YYYY-MM-DD")
  };
}

function goThisWeek() {
  const monday = dayjs()
    .subtract((dayjs().day() + 6) % 7, "day")
    .format("YYYY-MM-DD");
  query.value = {
    ...query.value,
    dateFrom: monday,
    dateTo: dayjs(monday).add(6, "day").format("YYYY-MM-DD")
  };
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

/** 热力格下钻：跳到当日时间轴流水（S5），保持同一数据中枢 */
function goTimeline(date: string | undefined) {
  if (!date) return;
  router.push(`/panorama/timeline?date=${date}`);
}

/** 热力格悬浮文案（抽成函数，避免模板内嵌套模板字符串） */
function heatTitle(
  day: { date: string } | undefined,
  time: string,
  count: number
): string {
  return `${day?.date ?? ""} ${time}：${count} 项`;
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

.range-title {
  min-width: 120px;
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tooltip-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

// 投屏模式：只放大字号与格子高度，不引入任何新配色（沿用语义变量）
.present-mode {
  .stat-item .stat-value {
    font-size: 32px;
  }

  .heat-cell {
    min-height: 40px;
    font-size: 15px;
  }
}

.stat-item {
  .stat-label {
    font-size: 13px;
    color: var(--el-text-color-secondary);
  }

  .stat-value {
    margin-top: 4px;
    font-size: 24px;
    font-weight: 500;
    color: var(--el-text-color-primary);

    small {
      font-size: 13px;
      color: var(--el-text-color-secondary);
    }
  }

  .stat-alert {
    color: var(--el-color-danger);
  }
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 12px;
  align-items: start;

  /* 窄屏单列堆叠：侧栏（告警/待办）不再被压成窄条 */
  @media (width <= 1100px) {
    grid-template-columns: 1fr;
  }
}

.side-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.heat-grid {
  display: grid;
  grid-template-columns: 64px repeat(7, minmax(0, 1fr));
  gap: 4px;
  min-width: 760px;
}

.heat-corner,
.heat-head,
.heat-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 4px 0;
}

.heat-cell {
  min-height: 28px;
  border-radius: 4px;
  background: var(--el-color-primary-light-8);
  color: var(--el-text-color-primary);
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;

  &.heat-empty {
    background: var(--el-fill-color-light);
  }
}

.alert-list,
.todo-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 13px;
  color: var(--el-text-color-regular);

  li {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.todo-list .todo-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
