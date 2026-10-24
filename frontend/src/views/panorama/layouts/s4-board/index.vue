<!-- S4 分组列表看板视图 /panorama/board -->
<!-- 定位：以「我接下来要做什么」驱动。适用：pm/admin 批量清待办、导出核对 -->
<!-- 唯一支持完整批量的布局（批量释放走串行单条接口 + 逐条汇总） -->
<template>
  <div class="biz-page">
    <el-card shadow="never" class="biz-toolbar-card">
      <div class="biz-toolbar">
        <div class="biz-toolbar-left">
          <el-button
            circle
            aria-label="上一周期"
            size="small"
            @click="shiftBy(-7)"
          >
            <IconifyIconOffline :icon="ArrowLeft" class="biz-nav-icon" />
          </el-button>
          <span class="biz-range-title">{{ rangeText }}</span>
          <el-button
            circle
            aria-label="下一周期"
            size="small"
            @click="shiftBy(7)"
          >
            <IconifyIconOffline :icon="ArrowRight" class="biz-nav-icon" />
          </el-button>
          <el-button size="small" text type="primary" @click="goThisWeek"
            >本周</el-button
          >
          <el-select v-model="groupBy" size="small" style="width: 110px">
            <el-option label="按版本" value="version" />
            <el-option label="按分支" value="branch" />
            <el-option label="按状态" value="status" />
          </el-select>
        </div>
        <div class="biz-toolbar-right">
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
        @update:version-id="setVersion"
        @update:branch-ids="setBranches"
        @update:scope="setScope"
        @open-my-bookings="actions.openMyBookings()"
        @refresh="refresh()"
      />
    </el-card>

    <div v-if="batchMode" class="batch-bar">
      <span class="biz-sub">已选 {{ selectedEvents.length }} 项</span>
      <el-button
        size="small"
        type="danger"
        :loading="actions.ui.batchReleasing"
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

    <!-- 首屏/翻周期加载：先出骨架，避免分组区整块空白（与 S2/S3/S5 同口径） -->
    <el-skeleton v-if="loading" :rows="4" animated />
    <template v-else>
      <el-card
        v-for="group in groups"
        :key="group.key"
        shadow="never"
        class="group-card biz-content-card"
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
              @click="toggleCollapse(group.key)"
            >
              {{ isCollapsed(group.key) ? "展开" : "收起" }}
            </el-button>
          </div>
        </template>
        <div v-show="!isCollapsed(group.key)" class="row-list">
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
                }}{{ e.endTime !== e.time ? `-${e.endTime}` : "" }}
                <!-- 按分支分组时组名即分支，行内不再重复 -->
                <template v-if="groupBy !== 'branch'">
                  · {{ e.branchName || "未关联分支" }}</template
                >
                · {{ e.subtitle }}
              </span>
            </span>
            <el-tag size="small" :type="tagType(e)" effect="plain">{{
              e.statusText
            }}</el-tag>
            <!-- 前两个操作常驻行内，其余进「更多」下拉（shared/EventActionMenu） -->
            <EventActionMenu :actions="rowActions(e)" />
          </div>
          <p v-if="group.events.length > 50" class="biz-tip">
            仅显示前 50 条，请缩小时间范围或使用筛选收敛。
          </p>
        </div>
      </el-card>

      <el-empty v-if="!groups.length" description="暂无调度数据" />
    </template>

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
import EventActionMenu from "../../shared/EventActionMenu.vue";
import ScheduleDialogs from "../../shared/ScheduleDialogs.vue";
import { buildEventActions } from "../../shared/eventActions";
import { borrowStatusMeta, bookingStatusMeta } from "@/views/constants";
import type { ScheduleEvent } from "../../types";

defineOptions({ name: "PanoramaBoardLayout" });

const {
  query,
  actions,
  loading,
  events,
  versionOptions,
  branchOptions,
  refresh,
  // 查询变更器统一走装配总线（R4-F9：删除本文件逐字复制的处理器副本）
  setVersion,
  setBranches,
  setScope,
  shiftBy,
  goThisWeek
} = usePanoramaPage();

const groupBy = ref<"version" | "branch" | "status">("version");
const batchMode = ref(false);
// 勾选只存事件 id：刷新/批量释放后 events 换新对象，按 id 派生选择集，
// 已消失的条目（如已释放的抢占）自动剔除，不会留在「已选 N 项」里被二次释放
const selectedIds = ref<Set<string>>(new Set());
const selectedEvents = computed(() =>
  events.value.filter(e => selectedIds.value.has(e.id))
);

// 折叠态外置（R5-F5）：此前挂在 computed 输出上（collapsed: false 内联 +
// 直接 mutate computed 结果），任何 events 更新（30s 轮询/刷新/筛选）都重建
// 数组导致用户收起的组全部弹开。与 selectedIds 同款按 group.key 记录。
const collapsedKeys = ref<Set<string>>(new Set());

function isCollapsed(key: string) {
  return collapsedKeys.value.has(key);
}

function toggleCollapse(key: string) {
  const next = new Set(collapsedKeys.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  collapsedKeys.value = next;
}

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
    // 按状态分组以 statusText（展示映射唯一来源）命名（R7-F6）：此前 key
    // 拼 e.status，组名 split 后直出英文枚举
    return `${e.source}|${e.statusText}`;
  };
  const map = new Map<string, ScheduleEvent[]>();
  for (const e of events.value) {
    const key = keyOf(e);
    (map.get(key) || map.set(key, []).get(key)!).push(e);
  }
  return [...map.entries()].map(([key, list]) => ({
    key,
    name: key.split("|")[1] ?? key,
    events: list
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

/** 行内操作：前两个常驻，其余进「更多」下拉（顺序见 shared/eventActions） */
function rowActions(e: ScheduleEvent) {
  return buildEventActions(e, actions);
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
</script>

<style scoped lang="scss">
.batch-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 12px;
  background: var(--el-color-warning-light-9);
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 8px;
}

/* biz-page 已有 12px gap，无需再叠加 margin-bottom */
.row-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.row {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 8px;
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
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;

  .row-title {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 13px;
    font-weight: 500;
    color: var(--el-text-color-primary);
    white-space: nowrap;
  }

  .row-sub {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    white-space: nowrap;
  }
}
</style>
