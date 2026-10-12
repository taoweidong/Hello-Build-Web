<!-- S5 时间轴流水视图 /panorama/timeline -->
<!-- 定位：单日纵向时间轴，把「那一刻发生了什么」串成可回溯的线 -->
<!-- 适用：tester 复盘冒烟冲突、admin 排查「谁在何时改了什么」、值班交接 -->
<template>
  <div class="biz-page">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button
            circle
            aria-label="前一天"
            size="small"
            @click="shiftDay(-1)"
          >
            <IconifyIconOffline :icon="ArrowLeft" class="nav-icon" />
          </el-button>
          <span class="day-title">{{ dayTitle }}</span>
          <el-button
            circle
            aria-label="后一天"
            size="small"
            @click="shiftDay(1)"
          >
            <IconifyIconOffline :icon="ArrowRight" class="nav-icon" />
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
        </div>
        <div class="tooltip-text">共 {{ rows.length }} 条</div>
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
    </el-card>

    <el-card shadow="never">
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
            </div>
            <div class="body-sub">
              {{ row.branchName || "未关联分支" }} · {{ row.subtitle }}
            </div>
            <div class="body-actions">
              <el-button
                v-if="row.permissions.canEdit"
                size="small"
                text
                type="primary"
                @click="actions.openEdit(row)"
                >修改</el-button
              >
              <el-button
                v-if="row.permissions.canBorrow"
                size="small"
                text
                type="primary"
                @click="actions.openBorrow(row)"
                >借用</el-button
              >
              <el-button
                v-if="row.permissions.canOccupy"
                size="small"
                text
                type="primary"
                @click="actions.openOccupy(row)"
                >抢占</el-button
              >
              <el-button
                v-if="row.permissions.canRelease"
                size="small"
                text
                type="danger"
                @click="actions.release(row)"
                >释放</el-button
              >
              <el-button
                v-if="row.permissions.canApprove"
                size="small"
                text
                type="primary"
                @click="actions.approve(row)"
                >通过</el-button
              >
              <el-button
                v-if="row.permissions.canApprove"
                size="small"
                text
                type="danger"
                @click="actions.reject(row)"
                >驳回</el-button
              >
              <el-button
                v-if="row.source === 'slot'"
                size="small"
                text
                @click="actions.openDetail(row)"
                >详情</el-button
              >
              <el-button
                v-if="row.source === 'borrow'"
                size="small"
                text
                @click="actions.copyText(row)"
                >复制</el-button
              >
            </div>
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
import ScheduleDialogs from "../../shared/ScheduleDialogs.vue";
import { detectCrossSourceConflicts } from "../../selectors";
import { borrowStatusMeta, bookingStatusMeta } from "@/views/constants";
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
  refresh
} = usePanoramaPage();

const filter = ref<"all" | "mine" | "conflict" | "borrow">("all");
const anchor = computed(() => query.value.dateFrom);
const dayTitle = computed(() => dayjs(anchor.value).format("YYYY年M月D日 ddd"));

const dayEvents = computed(() => byDay.value[anchor.value] ?? []);
const conflictIds = computed(
  () => new Set(detectCrossSourceConflicts(dayEvents.value).map(e => e.id))
);

const rows = computed(() => {
  let list = dayEvents.value;
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

/** 深链 ?date=YYYY-MM-DD（由 S1 热力格下钻带入） */
watch(
  () => route.query.date,
  value => {
    if (typeof value === "string" && dayjs(value).isValid()) {
      query.value = { ...query.value, dateFrom: value, dateTo: value };
    }
  },
  { immediate: true }
);

function shiftDay(delta: number) {
  const from = dayjs(anchor.value).add(delta, "day").format("YYYY-MM-DD");
  query.value = { ...query.value, dateFrom: from, dateTo: from };
}

function goToday() {
  const today = dayjs().format("YYYY-MM-DD");
  query.value = { ...query.value, dateFrom: today, dateTo: today };
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

.day-title {
  min-width: 150px;
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.tooltip-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.track {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
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
  padding: 8px 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;

  &.body-past {
    opacity: 0.55;
  }
}

.body-head {
  display: flex;
  align-items: center;
  gap: 8px;

  .body-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--el-text-color-primary);
  }
}

.body-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.body-actions {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
