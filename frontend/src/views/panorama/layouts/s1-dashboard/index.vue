<!-- S1 调度大屏态势视图 /panorama/dashboard -->
<!-- 定位：值不值得点进去看。适用：每日巡检 / 投屏 / 值班快速发现异常 -->
<template>
  <div class="biz-page" :class="{ 'present-mode': presentMode }">
    <el-card shadow="never" class="biz-toolbar-card">
      <div class="biz-toolbar">
        <div class="biz-toolbar-left">
          <el-button
            circle
            aria-label="上一周"
            size="small"
            @click="shiftBy(-7)"
          >
            <IconifyIconOffline :icon="ArrowLeft" class="biz-nav-icon" />
          </el-button>
          <span class="biz-range-title">{{ rangeText }}</span>
          <el-button
            circle
            aria-label="下一周"
            size="small"
            @click="shiftBy(7)"
          >
            <IconifyIconOffline :icon="ArrowRight" class="biz-nav-icon" />
          </el-button>
          <el-button size="small" text type="primary" @click="goThisWeek"
            >本周</el-button
          >
        </div>
        <div class="biz-toolbar-right">
          <span class="biz-toolbar-text">
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
        @update:version-id="setVersion"
        @update:branch-ids="setBranches"
        @update:scope="setScope"
        @open-my-bookings="actions.openMyBookings()"
        @refresh="refresh()"
      />
    </el-card>

    <div class="biz-stat-grid">
      <div class="biz-card biz-card-compact stat-item">
        <div class="stat-label">今日构建</div>
        <div class="stat-value">{{ kpi.todayBuild }}</div>
      </div>
      <div class="biz-card biz-card-compact stat-item">
        <div class="stat-label">本周抢占</div>
        <div class="stat-value">
          {{ kpi.weekSlotOccupied }}<small>/{{ kpi.weekSlotTotal }}</small>
        </div>
      </div>
      <div class="biz-card biz-card-compact stat-item">
        <div class="stat-label">待我审批</div>
        <div class="stat-value" :class="{ 'stat-alert': pendingApproval }">
          {{ pendingApproval }}
        </div>
      </div>
      <div class="biz-card biz-card-compact stat-item">
        <div class="stat-label">我的有效抢占</div>
        <div class="stat-value">{{ myReservedSlots }}</div>
      </div>
      <div class="biz-card biz-card-compact stat-item">
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
            <span class="biz-sub">
              占用率 {{ kpi.occupancyRate }}%
              <!-- 截断必须外化提示（R5-F7，对齐 slotTruncated 范式）：此前第 13 个
                   时刻起整行静默消失，会被误读为「该时刻无负载」 -->
              <template v-if="heatOverflow">
                · 仅展示前 {{ HEAT_MAX_ROWS }} 个时刻（共
                {{ heatPoints.length }} 个）
              </template>
            </span>
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
          <template v-else>
            <ul class="alert-list">
              <li v-for="c in conflicts.slice(0, ALERT_MAX_ROWS)" :key="c.id">
                <el-icon><WarningFilled /></el-icon>
                <span
                  >{{ c.date }} {{ c.time }}
                  {{ c.title }} 与已抢占时段重合</span
                >
              </li>
            </ul>
            <!-- KPI 卡冲突总数与列表条数不一致时必须说明去向（R5-F7） -->
            <p v-if="conflicts.length > ALERT_MAX_ROWS" class="biz-tip">
              另有 {{ conflicts.length - ALERT_MAX_ROWS }}
              条冲突未展示，可在「时间轴流水」用仅看冲突查看全部。
            </p>
          </template>
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
  kpi,
  versionOptions,
  branchOptions,
  todos,
  refresh,
  // 查询变更器统一走装配总线（R4-F9：删除本文件逐字复制的处理器副本）
  setVersion,
  setBranches,
  setScope,
  shiftBy,
  goThisWeek
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

/** 时刻 × 星期 热力：仅取范围内真实出现过的时刻，避免 24 行空行；
 *  行数上限截断时经 heatOverflow 外化提示（R5-F7，静默截断会误读为无负载） */
const HEAT_MAX_ROWS = 12;
/** 告警列表展示上限（超出部分给「另有 N 条」提示） */
const ALERT_MAX_ROWS = 8;
const heatPoints = computed(() => collectTimePoints(events.value));
const heatRows = computed(() =>
  buildHeatmap(
    events.value,
    days.value,
    heatPoints.value.slice(0, HEAT_MAX_ROWS)
  )
);
const heatOverflow = computed(() =>
  Math.max(heatPoints.value.length - HEAT_MAX_ROWS, 0)
);

/** 热力格下钻：跳到当日时间轴流水（S5），保持同一数据中枢 */
function goTimeline(date: string | undefined) {
  if (!date) return;
  // 对象写法交给 router 序列化 query（R4-F13/F-L5：不再模板串手拼 URL）
  router.push({ path: "/panorama/timeline", query: { date } });
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
/* 面板卡：压掉 el-card 默认 header/body 留白（子面板比页面主卡更紧一档） */
.panel {
  :deep(.el-card__header) {
    padding: 8px 12px;
  }

  :deep(.el-card__body) {
    padding: 10px 12px;
  }
}

/* 投屏模式：只放大字号与格子高度，不引入任何新配色（沿用语义变量） */
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
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .stat-value {
    margin-top: 2px;
    font-size: 22px;
    font-weight: 600;
    line-height: 1.2;
    color: var(--el-text-color-primary);

    small {
      font-size: 13px;
      font-weight: 400;
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
  padding: 4px 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
}

.heat-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  font-size: 12px;
  color: var(--el-text-color-primary);
  cursor: pointer;
  background: var(--el-color-primary-light-8);
  border-radius: 4px;

  &.heat-empty {
    background: var(--el-fill-color-light);
  }
}

.alert-list,
.todo-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0;
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
  list-style: none;

  li {
    display: flex;
    gap: 8px;
    align-items: center;
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
