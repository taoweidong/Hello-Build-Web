<!-- S2 时空甘特视图 /panorama/gantt -->
<!-- 定位：把线性时间还给调度。适用：pm 排查同版本跨分支互斥、integrator 找集成窗口 -->
<!-- 阶段区间一律取服务端 /plan 的 timeline（锚点日），其余日期退化为点标记，不硬算时长 -->
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
          <!-- 文案常显于开关右侧：inline-prompt 会把文案塞进滑块内，
               两种状态宽度不一导致工具条跳动，故不启用 -->
          <el-switch
            v-model="onlyBusy"
            size="small"
            active-text="仅看有任务分支"
          />
        </div>
        <div class="biz-toolbar-right">
          <el-tooltip placement="bottom">
            <template #content>
              锚点日展示四阶段区间，其余日期为时间点标记<br />
              更新于
              {{ lastLoadedAt ? formatTime(lastLoadedAt, "HH:mm:ss") : "—" }}
            </template>
            <el-icon class="hint-icon"><InfoFilled /></el-icon>
          </el-tooltip>
          <div class="biz-legend">
            <span v-for="s in STAGE_LEGEND" :key="s.key" class="legend-item">
              <i class="dot" :style="{ background: STAGE_COLORS[s.key] }" />{{
                s.label
              }}
            </span>
            <span class="legend-item"><i class="dot dot-slot" />抢占</span>
            <span class="legend-item"
              ><i class="diamond dot-borrow" />借用</span
            >
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

    <!-- 范围超 3 个自然月：抢占矩阵仅覆盖前 3 个月，显式提示避免误读为「无抢占」（R4-F13） -->
    <el-alert
      v-if="slotTruncated"
      title="范围过大，抢占矩阵仅展示前 3 个月"
      type="warning"
      :closable="false"
      show-icon
    />

    <el-card shadow="never" class="gantt-card biz-content-card">
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
            <div class="lane-track" :style="{ height: laneHeight(lane) }">
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
import InfoFilled from "~icons/ep/info-filled";
import { formatTime } from "@/utils/business";
// 中文星期唯一来源（R4-F6：dayjs `ddd` 依赖 zh-cn locale，本项目从未加载会中英混排）
import { WEEKDAY_CN_SUN } from "@/utils/week";
import { usePanoramaPage } from "../../usePanoramaPage";
import PanoramaFilterBar from "../../shared/PanoramaFilterBar.vue";
import ScheduleDialogs from "../../shared/ScheduleDialogs.vue";
import { groupByBranch, lanePack } from "../../selectors";
import { STAGE_COLORS } from "@/components/gantt/types";
import type { ScheduleEvent } from "../../types";

defineOptions({ name: "PanoramaGanttLayout" });

// 单日视图首屏锚今天（R5-F6）：此前吃 defaultWeekQuery 的周一~周日，锚点
// （query.dateFrom）落在本周一——周中打开看到的是历史日，需手点「今天」才能归位
const initialDay = dayjs().format("YYYY-MM-DD");

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
  shiftBy,
  goToday
} = usePanoramaPage({ dateFrom: initialDay, dateTo: initialDay });

const STAGE_LEGEND = [
  { key: "build", label: "构建" },
  { key: "smoke", label: "冒烟" },
  { key: "analysis", label: "分析" },
  { key: "push", label: "推送" }
];

const onlyBusy = ref(true);
const ticks = ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "24:00"];

const anchor = computed(() => query.value.dateFrom);
const dayTitle = computed(
  () =>
    `${dayjs(anchor.value).format("YYYY年M月D日")} ${WEEKDAY_CN_SUN[dayjs(anchor.value).day()]}`
);

/** 泳道：按分支分组走 selectors.groupByBranch 唯一实现（R4-F13/F-L2：删除内联
 * 重复分组）；空泳道可折叠（无虚拟滚动，控制 DOM 量），泳道内再 lanePack 分轨 */
const lanes = computed(() => {
  const dayEvents = byDay.value[anchor.value] ?? [];
  return groupByBranch(dayEvents)
    .map(g => ({
      key: `${g.branchId ?? "none"}`,
      name: g.branchName,
      count: g.events.length,
      events: g.events,
      lanes: lanePack(g.events).lanes
    }))
    .filter(l => !onlyBusy.value || l.count > 0)
    .sort((a, b) => b.count - a.count);
});

function pct(time: string): string {
  const [h, m] = time.split(":").map(Number);
  return `${(((h || 0) * 60 + (m || 0)) / 1440) * 100}%`;
}

/** 泳道高度按子轨道数伸缩（单轨 24px/条），避免固定 48px 的空白或多轨遮挡 */
function laneHeight(lane: { lanes: Map<string, number> }): string {
  const rows = lane.lanes.size ? Math.max(...lane.lanes.values()) + 1 : 1;
  return `${rows * 24 + 2}px`;
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
    top: `${subLane * 24 + 1}px`,
    background: e.kind === "push" ? "transparent" : color,
    borderColor: color,
    borderStyle: e.kind === "push" ? "dashed" : "solid"
  };
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
.hint-icon {
  font-size: 14px;
  color: var(--el-text-color-placeholder);
  cursor: help;
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
  gap: 4px;
}

.ruler,
.lane {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}

.ruler-label,
.lane-label {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--el-text-color-regular);
  white-space: nowrap;

  small {
    color: var(--el-text-color-secondary);
  }
}

/* 轨道高度由 laneHeight() 内联控制（按子轨道数伸缩），此处只给兜底最小高度 */
.ruler-track,
.lane-track {
  position: relative;
  min-height: 26px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
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
  font-size: 11px;
  color: var(--el-text-color-secondary);
  transform: translateX(-50%);
}

/* 末位刻度（24:00）右缘对齐轨道末端：默认居中会有一半溢出，
   在 overflow-x:auto 容器里撑出一段无意义的横向滚动 */
.ruler-track .tick:last-child {
  transform: translateX(-100%);
}

.bar {
  position: absolute;
  display: flex;
  align-items: center;
  height: 22px;
  padding: 0 4px;
  overflow: hidden;
  font-size: 11px;
  // 彩底白字走 Element Plus 语义变量（不写死 hex，深浅色均不破面）
  color: var(--el-color-white);
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: 4px;

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
    text-decoration: line-through;
    opacity: 0.45;
  }

  &.bar-borrow {
    color: var(--el-color-warning);
    background: var(--el-color-warning-light-9);
    border-style: solid;
  }
}
</style>
