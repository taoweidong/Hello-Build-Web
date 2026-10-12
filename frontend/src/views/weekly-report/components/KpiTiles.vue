<template>
  <section class="kpi-row">
    <article
      v-for="(tile, i) in tiles"
      :key="tile.key"
      class="kpi-tile wk-panel wk-enter"
      :style="{ animationDelay: `${i * 60}ms` }"
    >
      <div class="kpi-main">
        <span class="kpi-icon" :class="tile.tone">
          <IconifyIconOffline :icon="tile.icon" />
        </span>
        <div class="kpi-text">
          <b class="kpi-value">{{ tile.value }}</b>
          <span class="kpi-label">{{ tile.label }}</span>
        </div>
      </div>
      <p class="kpi-sub">
        <template v-if="tile.progress !== undefined">
          <span class="kpi-bar">
            <span
              class="kpi-bar-fill"
              :class="tile.tone"
              :style="{ width: `${tile.progress}%` }"
            />
          </span>
          {{ tile.sub }}
        </template>
        <template v-else>{{ tile.sub }}</template>
      </p>
    </article>
  </section>
</template>

<script setup lang="ts">
// 顶部 KPI 磁贴：策略任务 / 构建任务 / 推送任务 / 今日待执行
// 数据来自 computeKpis（纯函数，单测锁定），不新增接口
// 配色走 Element Plus 语义色板（primary/success/warning/danger），与系统一致
import { computed } from "vue";
import type { WeeklyKpis } from "@/utils/weeklyReport";
import BoxIcon from "~icons/ep/box";
import CpuIcon from "~icons/ep/cpu";
// 推送用上传意象图标
import UploadIcon from "~icons/ep/upload";
import TimerIcon from "~icons/ep/timer";

defineOptions({ name: "WeeklyReportKpiTiles" });

const props = defineProps<{ kpis: WeeklyKpis }>();

/** 图标/进度条色调，对应 EP 语义色 */
type TileTone = "primary" | "success" | "warning" | "danger";

interface Tile {
  key: string;
  icon: unknown;
  label: string;
  value: string;
  sub: string;
  progress?: number;
  tone: TileTone;
}

const tiles = computed<Tile[]>(() => [
  {
    key: "tasks",
    icon: BoxIcon,
    label: "策略任务",
    value: String(props.kpis.tasks),
    sub: `覆盖 ${props.kpis.timePoints} 个时间点 · ${props.kpis.branchCount}/${props.kpis.branchTotal} 分支`,
    tone: "primary"
  },
  {
    key: "build",
    icon: CpuIcon,
    label: "构建任务",
    value: String(props.kpis.buildTasks),
    sub: `最早 ${props.kpis.earliestBuild} · 最晚 ${props.kpis.latestBuild}`,
    tone: "success"
  },
  {
    key: "push",
    icon: UploadIcon,
    label: "推送任务",
    value: String(props.kpis.pushTasks),
    sub: `同步 ${props.kpis.syncPush} · 正常流程 ${props.kpis.normalPush}`,
    tone: "warning"
  },
  {
    key: "today",
    icon: TimerIcon,
    label: "今日待执行",
    value: String(props.kpis.todayPending),
    sub: `已完成 ${props.kpis.todayDone} 项`,
    progress: props.kpis.tasks
      ? Math.round((props.kpis.todayDone / props.kpis.tasks) * 100)
      : 0,
    tone: "danger"
  }
]);
</script>

<style scoped lang="scss">
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.kpi-tile {
  gap: 10px;
  padding: 14px 16px;
}

.kpi-tile:hover {
  border-color: var(--wk-accent-border);
  box-shadow: var(--el-box-shadow-light);
}

.kpi-main {
  display: flex;
  gap: 12px;
  align-items: center;
}

/* 图标 chip：EP 语义色淡底 + 同色图标（对齐系统统计卡样式） */
.kpi-icon {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  font-size: 20px;
  border-radius: var(--el-border-radius-base);
}

.kpi-icon.primary {
  color: var(--wk-accent);
  background: var(--wk-accent-light);
}

.kpi-icon.success {
  color: var(--wk-mint);
  background: var(--wk-mint-light);
}

.kpi-icon.warning {
  color: var(--wk-amber);
  background: var(--wk-amber-light);
}

.kpi-icon.danger {
  color: var(--wk-danger);
  background: var(--wk-danger-light);
}

.kpi-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.kpi-value {
  font-size: 26px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
  color: var(--wk-text-1);
  letter-spacing: 0.01em;
}

.kpi-label {
  margin-top: 2px;
  font-size: 12px;
  color: var(--wk-text-3);
}

.kpi-sub {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0;
  font-size: 12px;
  color: var(--wk-text-2);
}

.kpi-bar {
  flex: none;
  width: 56px;
  height: 4px;
  overflow: hidden;
  background: var(--el-border-color-lighter);
  border-radius: 999px;
}

.kpi-bar-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width 0.6s cubic-bezier(0.22, 0.61, 0.36, 1);
}

.kpi-bar-fill.primary {
  background: var(--wk-accent);
}

.kpi-bar-fill.success {
  background: var(--wk-mint);
}

.kpi-bar-fill.warning {
  background: var(--wk-amber);
}

.kpi-bar-fill.danger {
  background: var(--wk-danger);
}

@media (width <= 1200px) {
  .kpi-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (width <= 560px) {
  .kpi-tile {
    padding: 12px;
  }

  .kpi-value {
    font-size: 22px;
  }
}
</style>
