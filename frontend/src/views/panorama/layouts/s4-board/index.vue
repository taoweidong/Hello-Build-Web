<!-- S4 分组列表看板视图 /panorama/board -->
<!-- 定位：以「我接下来要做什么」驱动。适用：pm/admin 批量清待办、导出核对 -->
<!-- 唯一支持完整批量的布局（批量释放走串行单条接口 + 逐条汇总） -->
<template>
  <div class="biz-page">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button
            circle
            aria-label="上一周期"
            size="small"
            @click="shiftRange(-1)"
          >
            <IconifyIconOffline :icon="ArrowLeft" class="nav-icon" />
          </el-button>
          <span class="range-title">{{ rangeText }}</span>
          <el-button
            circle
            aria-label="下一周期"
            size="small"
            @click="shiftRange(1)"
          >
            <IconifyIconOffline :icon="ArrowRight" class="nav-icon" />
          </el-button>
          <el-button size="small" text type="primary" @click="goThisWeek"
            >本周</el-button
          >
          <span class="biz-sub">分组</span>
          <el-select v-model="groupBy" size="small" style="width: 120px">
            <el-option label="按版本" value="version" />
            <el-option label="按分支" value="branch" />
            <el-option label="按状态" value="status" />
          </el-select>
        </div>
        <div class="toolbar-left">
          <el-button size="small" @click="toggleBatch">
            {{ batchMode ? "退出批量" : "批量模式" }}
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
    </el-card>

    <div v-if="batchMode" class="batch-bar">
      <span class="biz-sub">已选 {{ selectedEvents.length }} 项</span>
      <el-button
        size="small"
        type="danger"
        :disabled="!selectedEvents.length"
        @click="actions.batchRelease(selectedEvents)"
      >
        批量释放
      </el-button>
      <el-button
        size="small"
        :disabled="!selectedEvents.length"
        @click="selectedIds = new Set()"
      >
        清空选择
      </el-button>
    </div>

    <el-card
      v-for="group in groups"
      :key="group.key"
      shadow="never"
      class="group-card"
    >
      <template #header>
        <div class="biz-card-head">
          <span class="biz-card-title">
            {{ group.name }}
            <el-tag size="small" type="info" effect="plain">{{
              group.events.length
            }}</el-tag>
          </span>
          <el-button
            size="small"
            text
            type="primary"
            @click="group.collapsed = !group.collapsed"
          >
            {{ group.collapsed ? "展开" : "收起" }}
          </el-button>
        </div>
      </template>
      <div v-show="!group.collapsed" class="row-list">
        <div v-for="e in group.events.slice(0, 50)" :key="e.id" class="row">
          <el-checkbox
            v-if="batchMode"
            :model-value="isSelected(e)"
            @update:model-value="toggleSelect(e, $event)"
          />
          <span class="row-color" :style="{ background: e.color }" />
          <span class="row-main">
            <span class="row-title">{{ e.title }}</span>
            <span class="row-sub">
              {{ e.date }} {{ e.time
              }}{{ e.endTime !== e.time ? `-${e.endTime}` : "" }} ·
              {{ e.branchName || "未关联分支" }} ·
              {{ e.subtitle }}
            </span>
          </span>
          <el-tag size="small" :type="tagType(e)" effect="plain">{{
            e.statusText
          }}</el-tag>
          <span class="row-actions">
            <el-button
              v-if="e.permissions.canEdit"
              size="small"
              text
              type="primary"
              @click="actions.openEdit(e)"
              >修改</el-button
            >
            <el-button
              v-if="e.permissions.canBorrow"
              size="small"
              text
              type="primary"
              @click="actions.openBorrow(e)"
              >借用</el-button
            >
            <el-button
              v-if="e.permissions.canOccupy"
              size="small"
              text
              type="primary"
              @click="actions.openOccupy(e)"
              >抢占</el-button
            >
            <el-button
              v-if="e.permissions.canRelease"
              size="small"
              text
              type="danger"
              @click="actions.release(e)"
              >释放</el-button
            >
            <el-button
              v-if="e.permissions.canApprove"
              size="small"
              text
              type="primary"
              @click="actions.approve(e)"
              >通过</el-button
            >
            <el-button
              v-if="e.permissions.canApprove"
              size="small"
              text
              type="danger"
              @click="actions.reject(e)"
              >驳回</el-button
            >
            <el-button
              v-if="e.source === 'slot'"
              size="small"
              text
              @click="actions.openDetail(e)"
              >详情</el-button
            >
          </span>
        </div>
        <p v-if="group.events.length > 50" class="biz-tip">
          仅显示前 50 条，请缩小时间范围或使用筛选收敛。
        </p>
      </div>
    </el-card>

    <el-empty v-if="!groups.length && !loading" description="暂无调度数据" />

    <ScheduleDialogs />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import dayjs from "dayjs";
import ArrowLeft from "~icons/ep/arrow-left";
import ArrowRight from "~icons/ep/arrow-right";
import { usePanoramaPage } from "../../usePanoramaPage";
import PanoramaFilterBar from "../../shared/PanoramaFilterBar.vue";
import ScheduleDialogs from "../../shared/ScheduleDialogs.vue";
import { borrowStatusMeta, bookingStatusMeta } from "@/views/constants";
import type { ScheduleEvent } from "../../types";

defineOptions({ name: "PanoramaBoardLayout" });

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

const groupBy = ref<"version" | "branch" | "status">("version");
const batchMode = ref(false);
// 勾选只存事件 id：刷新/批量释放后 events 换新对象，按 id 派生选择集，
// 已消失的条目（如已释放的抢占）自动剔除，不会留在「已选 N 项」里被二次释放
const selectedIds = ref<Set<string>>(new Set());
const selectedEvents = computed(() =>
  events.value.filter(e => selectedIds.value.has(e.id))
);

const rangeText = computed(
  () =>
    `${dayjs(query.value.dateFrom).format("M月D日")} - ${dayjs(
      query.value.dateTo
    ).format("M月D日")}`
);

const groups = computed(() => {
  const keyOf = (e: ScheduleEvent) => {
    if (groupBy.value === "version")
      return `${e.versionId ?? "none"}|${e.versionName || "未关联版本"}`;
    if (groupBy.value === "branch")
      return `${e.branchId ?? "none"}|${e.branchName || "未关联分支"}`;
    return `${e.source}|${e.status}|${e.statusText}`;
  };
  const map = new Map<string, ScheduleEvent[]>();
  for (const e of events.value) {
    const key = keyOf(e);
    (map.get(key) || map.set(key, []).get(key)!).push(e);
  }
  return [...map.entries()].map(([key, list]) => ({
    key,
    name: key.split("|")[1] ?? key,
    events: list,
    collapsed: false
  }));
});

function tagType(
  e: ScheduleEvent
): "success" | "danger" | "warning" | "info" | "primary" {
  if (e.source === "borrow") return borrowStatusMeta(e.status).type;
  if (e.source === "slot") return bookingStatusMeta(e.status).type;
  if (e.past) return "info";
  return "primary";
}

function isSelected(e: ScheduleEvent) {
  return selectedIds.value.has(e.id);
}

function toggleSelect(e: ScheduleEvent, value: string | number | boolean) {
  const checked = value === true || value === "";
  const next = new Set(selectedIds.value);
  if (checked) next.add(e.id);
  else next.delete(e.id);
  selectedIds.value = next;
}

function toggleBatch() {
  batchMode.value = !batchMode.value;
  if (!batchMode.value) selectedIds.value = new Set();
}

function shiftRange(delta: number) {
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

.batch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 8px;
  background: var(--el-color-warning-light-9);
}

.group-card {
  margin-bottom: 12px;
}

.row-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;

  &:hover {
    background: var(--el-fill-color-light);
  }
}

.row-color {
  flex: none;
  width: 4px;
  height: 24px;
  border-radius: 2px;
}

.row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;

  .row-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--el-text-color-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .row-sub {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.row-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: none;
}
</style>
