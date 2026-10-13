<!-- S2 时空甘特视图 /panorama/gantt -->
<!-- 定位：把线性时间还给调度。适用：pm 排查同版本跨分支互斥、integrator 找集成窗口 -->
<!-- 阶段区间一律取服务端 /plan 的 timeline（锚点日），其余日期退化为点标记，不硬算时长 -->
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
          <el-switch
            v-model="onlyBusy"
            size="small"
            active-text="仅看有任务分支"
            inline-prompt
          />
        </div>
        <div class="tooltip-text">
          锚点日展示四阶段区间，其余日期为时间点标记
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
        <span v-for="s in STAGE_LEGEND" :key="s.key" class="legend-item">
          <i class="dot" :style="{ background: STAGE_COLORS[s.key] }" />{{
            s.label
          }}
        </span>
        <span class="legend-item"><i class="dot dot-slot" />已抢占时段</span>
        <span class="legend-item"
          ><i class="diamond dot-borrow" />待审借用</span
        >
      </div>
    </el-card>

    <el-card shadow="never" class="gantt-card">
      <el-skeleton v-if="loading" :rows="6" animated />
      <el-empty v-else-if="!lanes.length" description="该日暂无调度数据" />
      <div v-else class="gantt-scroll">
        <div class="gantt" :style="{ minWidth: '1100px' }">
          <div class="ruler">
            <div class="ruler-label">时间</div>
            <div class="ruler-track">
              <span
                v-for="t in ticks"
                :key="t"
                class="tick"
                :style="{ left: pct(t) }"
              >
                {{ t }}
              </span>
            </div>
          </div>
          <div v-for="lane in lanes" :key="lane.key" class="lane">
            <div class="lane-label" :title="lane.name">
              {{ lane.name }}
              <small v-if="lane.count">（{{ lane.count }}）</small>
            </div>
            <div class="lane-track">
              <div
                v-for="e in lane.events"
                :key="e.id"
                class="bar"
                :class="{
                  'bar-point': e.durationMin === 0,
                  'bar-past': e.past,
                  'bar-borrow': e.source === 'borrow'
                }"
                :style="barStyle(e, lane.lanes.get(e.id) ?? 0)"
                :title="barTitle(e)"
                @click="onBarClick(e)"
              >
                <span class="bar-text">{{ e.title }}</span>
              </div>
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
import { ElMessage } from "element-plus";
import ArrowLeft from "~icons/ep/arrow-left";
import ArrowRight from "~icons/ep/arrow-right";
import { usePanoramaPage } from "../../usePanoramaPage";
import PanoramaFilterBar from "../../shared/PanoramaFilterBar.vue";
import ScheduleDialogs from "../../shared/ScheduleDialogs.vue";
import { lanePack } from "../../selectors";
import { STAGE_COLORS } from "@/components/gantt/types";
import type { ScheduleEvent } from "../../types";

defineOptions({ name: "PanoramaGanttLayout" });

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

const STAGE_LEGEND = [
  { key: "build", label: "构建" },
  { key: "smoke", label: "冒烟" },
  { key: "analysis", label: "分析" },
  { key: "push", label: "推送" }
];

const onlyBusy = ref(true);
const ticks = ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "24:00"];

const anchor = computed(() => query.value.dateFrom);
const dayTitle = computed(() => dayjs(anchor.value).format("YYYY年M月D日 ddd"));

/** 泳道：按分支分组；空泳道可折叠（无虚拟滚动，控制 DOM 量） */
const lanes = computed(() => {
  const dayEvents = byDay.value[anchor.value] ?? [];
  const map = new Map<string, ScheduleEvent[]>();
  for (const e of dayEvents) {
    const key = `${e.branchId ?? "none"}`;
    (map.get(key) || map.set(key, []).get(key)!).push(e);
  }
  return [...map.entries()]
    .map(([key, list]) => {
      const { lanes: subLanes } = lanePack(list);
      return {
        key,
        name: list[0].branchName || "未关联分支",
        count: list.length,
        events: list,
        lanes: subLanes
      };
    })
    .filter(l => !onlyBusy.value || l.count > 0)
    .sort((a, b) => b.count - a.count);
});

function pct(time: string): string {
  const [h, m] = time.split(":").map(Number);
  return `${(((h || 0) * 60 + (m || 0)) / 1440) * 100}%`;
}

/** 甘特条悬浮文案（抽成函数，避免模板内嵌套模板字符串） */
function barTitle(e: ScheduleEvent): string {
  const range = e.endTime !== e.time ? `${e.time}-${e.endTime}` : e.time;
  return `${range} ${e.title}`;
}

/** 甘特条定位：left = 起始占比，width = 时长占比（点事件最小 1.2%，避免不可点） */
function barStyle(e: ScheduleEvent, subLane: number) {
  const [sh, sm] = e.time.split(":").map(Number);
  const start = (sh || 0) * 60 + (sm || 0);
  const dur = e.durationMin > 0 ? e.durationMin : 0;
  const width = dur > 0 ? (dur / 1440) * 100 : 1.2;
  const color =
    e.source === "slot"
      ? e.color
      : e.source === "borrow"
        ? "var(--el-color-warning)"
        : e.color;
  return {
    left: `${(start / 1440) * 100}%`,
    width: `${width}%`,
    top: `${subLane * 26}px`,
    background: e.kind === "push" ? "transparent" : color,
    borderColor: color,
    borderStyle: e.kind === "push" ? "dashed" : "solid"
  };
}

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

async function onBarClick(e: ScheduleEvent) {
  if (e.past) {
    ElMessage.info("该日程已过期，仅可查看");
    return;
  }
  if (e.source === "slot") {
    if (e.permissions.canOccupy) actions.openOccupy(e);
    else actions.openDetail(e);
    return;
  }
  if (e.source === "borrow") {
    // 审批人进抽屉批；申请人进抽屉撤回（P2-R1）
    if (e.permissions.canApprove || e.permissions.canCancel)
      actions.openApproval();
    else ElMessage.info("该借用申请待审批中");
    return;
  }
  if (e.permissions.canEdit) await actions.openEdit(e);
  else await actions.openBorrow(e);
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
  }

  .diamond {
    border-radius: 2px;
    transform: rotate(45deg);
  }

  .dot-slot {
    background: var(--el-color-success);
  }

  .dot-borrow {
    background: var(--el-color-warning);
  }
}

.gantt-card {
  overflow: hidden;
}

.gantt-scroll {
  overflow-x: auto;
}

.gantt {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ruler,
.lane {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}

.ruler-label,
.lane-label {
  font-size: 13px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  small {
    color: var(--el-text-color-secondary);
  }
}

.ruler-track,
.lane-track {
  position: relative;
  height: 48px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
}

.ruler-track {
  height: 22px;
  background: transparent;
  border-bottom: 1px solid var(--el-border-color-lighter);
  border-radius: 0;
}

.tick {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.bar {
  position: absolute;
  height: 22px;
  border: 1px solid transparent;
  border-radius: 4px;
  // 彩底白字走 Element Plus 语义变量（不写死 hex，深浅色均不破面）
  color: var(--el-color-white);
  font-size: 11px;
  display: flex;
  align-items: center;
  padding: 0 4px;
  overflow: hidden;
  cursor: pointer;

  .bar-text {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &.bar-point {
    height: 10px;
    color: var(--el-text-color-primary);
    background: var(--el-fill-color);
  }

  &.bar-past {
    opacity: 0.45;
    text-decoration: line-through;
  }

  &.bar-borrow {
    background: var(--el-color-warning-light-9);
    color: var(--el-color-warning);
    border-style: solid;
  }
}
</style>
