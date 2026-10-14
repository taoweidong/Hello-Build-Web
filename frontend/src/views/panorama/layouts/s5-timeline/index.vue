<!-- S5 时间轴流水视图 /panorama/timeline -->
<!-- 定位：单日纵向时间轴，把「那一刻发生了什么」串成可回溯的线 -->
<!-- 适用：tester 复盘冒烟冲突、admin 排查「谁在何时改了什么」、值班交接 -->
<template>
  <div class="biz-page">
    <el-card shadow="never" class="biz-toolbar-card">
      <div class="biz-toolbar">
        <div class="biz-toolbar-left">
          <el-button
            circle
            aria-label="前一天"
            size="small"
            @click="shiftBy(-1)"
          >
            <IconifyIconOffline :icon="ArrowLeft" class="biz-nav-icon" />
          </el-button>
          <span class="biz-range-title">{{ dayTitle }}</span>
          <el-button
            circle
            aria-label="后一天"
            size="small"
            @click="shiftBy(1)"
          >
            <IconifyIconOffline :icon="ArrowRight" class="biz-nav-icon" />
          </el-button>
          <el-button size="small" text type="primary" @click="goToday"
            >今天</el-button
          >
          <el-radio-group v-model="filter" size="small">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="mine">只看我的</el-radio-button>
            <el-radio-button value="conflict">只看冲突</el-radio-button>
            <el-radio-button value="borrow">只看借用</el-radio-button>
          </el-radio-group>
          <el-checkbox v-model="hideAvailable" size="small">
            折叠空闲时段
          </el-checkbox>
        </div>
        <div class="biz-toolbar-text">共 {{ rows.length }} 条</div>
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

    <!-- 范围超 3 个自然月：抢占矩阵仅覆盖前 3 个月，显式提示避免误读为「无抢占」（R4-F13） -->
    <el-alert
      v-if="slotTruncated"
      title="范围过大，抢占矩阵仅展示前 3 个月"
      type="warning"
      :closable="false"
      show-icon
    />

    <el-card shadow="never" class="biz-content-card">
      <el-skeleton v-if="loading" :rows="8" animated />
      <el-empty v-else-if="!rows.length" description="当日暂无调度流水" />
      <ol v-else class="track">
        <li v-for="row in rows" :key="row.id" class="track-item">
          <div class="track-time">
            <span class="time-main">{{ row.time }}</span>
            <span v-if="row.endTime !== row.time" class="time-sub">{{
              row.endTime
            }}</span>
          </div>
          <span class="track-dot" :style="{ background: row.color }" />
          <div class="track-body" :class="{ 'body-past': row.past }">
            <div class="body-head">
              <span class="body-title">{{ row.title }}</span>
              <el-tag size="small" :type="tagType(row)" effect="plain">{{
                row.statusText
              }}</el-tag>
              <el-tag
                v-if="conflictIds.has(row.id)"
                size="small"
                type="danger"
                effect="dark"
                >重合</el-tag
              >
              <!-- 次要信息并入标题行尾部弱化展示，条目从三行压到两行 -->
              <span class="body-sub">
                {{ row.branchName || "未关联分支" }} · {{ row.subtitle }}
              </span>
            </div>
            <!-- 前两个操作常驻行内，其余进「更多」下拉（shared/EventActionMenu） -->
            <EventActionMenu :actions="rowActions(row)" />
          </div>
        </li>
      </ol>
    </el-card>

    <ScheduleDialogs />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import dayjs from "dayjs";
import ArrowLeft from "~icons/ep/arrow-left";
import ArrowRight from "~icons/ep/arrow-right";
import { usePanoramaPage } from "../../usePanoramaPage";
import PanoramaFilterBar from "../../shared/PanoramaFilterBar.vue";
import EventActionMenu from "../../shared/EventActionMenu.vue";
import ScheduleDialogs from "../../shared/ScheduleDialogs.vue";
import { buildEventActions, withCopyAction } from "../../shared/eventActions";
import { detectCrossSourceConflicts } from "../../selectors";
import { borrowStatusMeta, bookingStatusMeta } from "@/views/constants";
// 中文星期唯一来源（R4-F6：dayjs `ddd` 依赖 zh-cn locale，本项目从未加载会中英混排）
import { WEEKDAY_CN_SUN } from "@/utils/week";
import type { ScheduleEvent } from "../../types";

defineOptions({ name: "PanoramaTimelineLayout" });

const route = useRoute();
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
  slotTruncated,
  refresh,
  // 查询变更器统一走装配总线（R4-F9：删除本文件逐字复制的处理器副本）
  setVersion,
  setBranches,
  setScope,
  setDateRange,
  shiftBy,
  goToday
} = usePanoramaPage();

const filter = ref<"all" | "mine" | "conflict" | "borrow">("all");
/** 折叠空闲时段：隐藏「空闲可抢占」的时段行，把注意力收敷到已占用/待办上 */
const hideAvailable = ref(false);
const anchor = computed(() => query.value.dateFrom);
const dayTitle = computed(
  () =>
    `${dayjs(anchor.value).format("YYYY年M月D日")} ${WEEKDAY_CN_SUN[dayjs(anchor.value).day()]}`
);

const dayEvents = computed(() => byDay.value[anchor.value] ?? []);
const conflictIds = computed(
  () => new Set(detectCrossSourceConflicts(dayEvents.value).map(e => e.id))
);

const rows = computed(() => {
  let list = dayEvents.value;
  if (hideAvailable.value)
    list = list.filter(e => !(e.source === "slot" && e.status === "available"));
  if (filter.value === "mine") list = list.filter(e => e.mine);
  if (filter.value === "borrow") list = list.filter(e => e.source === "borrow");
  if (filter.value === "conflict")
    list = list.filter(e => conflictIds.value.has(e.id));
  return list;
});

function tagType(
  e: ScheduleEvent
): "success" | "danger" | "warning" | "info" | "primary" {
  if (e.source === "borrow") return borrowStatusMeta(e.status).type;
  if (e.source === "slot") return bookingStatusMeta(e.status).type;
  if (e.past) return "info";
  return "primary";
}

/** 行内操作：前两个常驻，其余进「更多」下拉；
 *  借用事件额外带「复制」（S4 看板不提供） */
function rowActions(e: ScheduleEvent) {
  return withCopyAction(buildEventActions(e, actions), e, actions);
}

/** 深链 ?date=YYYY-MM-DD（由 S1 热力格下钻带入） */
watch(
  () => route.query.date,
  value => {
    if (typeof value === "string" && dayjs(value).isValid()) {
      setDateRange(value, value);
    }
  },
  { immediate: true }
);
</script>

<style scoped lang="scss">
.track {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.track-item {
  display: grid;
  grid-template-columns: 64px 12px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.track-time {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-size: 12px;
  color: var(--el-text-color-secondary);

  .time-main {
    font-size: 14px;
    font-weight: 500;
    color: var(--el-text-color-primary);
  }
}

.track-dot {
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 50%;
}

.track-body {
  padding: 6px 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;

  &.body-past {
    opacity: 0.55;
  }
}

.body-head {
  display: flex;
  gap: 8px;
  align-items: center;

  .body-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--el-text-color-primary);
  }
}

/* 次要信息行内弱化：标题行尾部单行省略，不再独占一行 */
.body-sub {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  white-space: nowrap;
}

/* 操作组与标题行的间距：EventActionMenu 根元素带本页 scope 属性，可直接选中 */
.track-body > .action-group {
  margin-top: 4px;
}
</style>
