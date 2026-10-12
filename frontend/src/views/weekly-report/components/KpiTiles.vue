<template>
  <section class="kpi-row">
    <article
      v-for="(tile, i) in tiles"
      :key="tile.key"
      class="kpi-tile wk-panel wk-enter"
      :style="{ animationDelay: `${i * 60}ms` }"
    >
      <!-- 角落水印大图标（低透明度装饰） -->
      <IconifyIconOffline :icon="tile.icon" class="kpi-watermark" />
      <div class="kpi-main">
        <span
          class="kpi-icon"
          :style="{
            color: tile.color,
            background: tile.tint,
            borderColor: tile.border
          }"
        >
          <IconifyIconOffline :icon="tile.icon" />
        </span>
        <div class="kpi-text">
          <b class="kpi-value" :style="{ backgroundImage: tile.grad }">{{
            tile.value
          }}</b>
          <span class="kpi-label">{{ tile.label }}</span>
        </div>
      </div>
      <p class="kpi-sub">
        <template v-if="tile.progress !== undefined">
          <span class="kpi-bar">
            <span
              class="kpi-bar-fill"
              :style="{ width: `${tile.progress}%`, background: tile.grad }"
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
import { computed } from "vue";
import type { WeeklyKpis } from "@/utils/weeklyReport";
import BoxIcon from "~icons/ep/box";
import CpuIcon from "~icons/ep/cpu";
// 推送用上传意象图标
import UploadIcon from "~icons/ep/upload";
import TimerIcon from "~icons/ep/timer";

defineOptions({ name: "WeeklyReportKpiTiles" });

const props = defineProps<{ kpis: WeeklyKpis }>();

interface Tile {
  key: string;
  icon: unknown;
  label: string;
  value: string;
  sub: string;
  progress?: number;
  color: string;
  tint: string;
  border: string;
  grad: string;
}

const tiles = computed<Tile[]>(() => [
  {
    key: "tasks",
    icon: BoxIcon,
    label: "策略任务",
    value: String(props.kpis.tasks),
    sub: `覆盖 ${props.kpis.timePoints} 个时间点 · ${props.kpis.branchCount}/${props.kpis.branchTotal} 分支`,
    color: "var(--wk-cyan)",
    tint: "rgb(56 189 248 / 12%)",
    border: "rgb(56 189 248 / 35%)",
    grad: "linear-gradient(180deg, #7dd9fb, #38bdf8)"
  },
  {
    key: "build",
    icon: CpuIcon,
    label: "构建任务",
    value: String(props.kpis.buildTasks),
    sub: `最早 ${props.kpis.earliestBuild} · 最晚 ${props.kpis.latestBuild}`,
    color: "var(--wk-indigo)",
    tint: "rgb(129 140 248 / 12%)",
    border: "rgb(129 140 248 / 35%)",
    grad: "linear-gradient(180deg, #aeb6fd, #818cf8)"
  },
  {
    key: "push",
    icon: UploadIcon,
    label: "推送任务",
    value: String(props.kpis.pushTasks),
    sub: `同步 ${props.kpis.syncPush} · 正常流程 ${props.kpis.normalPush}`,
    color: "var(--wk-violet)",
    tint: "rgb(167 139 250 / 12%)",
    border: "rgb(167 139 250 / 35%)",
    grad: "linear-gradient(180deg, #c4b2fd, #a78bfa)"
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
    color: "var(--wk-emerald)",
    tint: "rgb(52 211 153 / 12%)",
    border: "rgb(52 211 153 / 35%)",
    grad: "linear-gradient(180deg, #6ee7b7, #34d399)"
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
  position: relative;
  gap: 10px;
  padding: 14px 16px;
  overflow: hidden;
  transition:
    transform 0.25s,
    box-shadow 0.25s,
    border-color 0.25s;
}

/* 顶部渐变发丝线 */
.kpi-tile::before {
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  content: "";
  background: linear-gradient(
    90deg,
    transparent,
    rgb(56 189 248 / 55%),
    rgb(129 140 248 / 45%),
    transparent
  );
}

.kpi-tile:hover {
  border-color: var(--wk-border-strong);
  box-shadow:
    var(--wk-shadow-panel),
    0 0 24px -8px rgb(56 189 248 / 45%);
  transform: translateY(-2px);
}

.kpi-watermark {
  position: absolute;
  right: -10px;
  bottom: -14px;
  font-size: 76px;
  color: #fff;
  pointer-events: none;
  opacity: 0.05;
}

.kpi-main {
  display: flex;
  gap: 12px;
  align-items: center;
}

.kpi-icon {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  font-size: 20px;
  border: 1px solid;
  border-radius: 11px;
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
  letter-spacing: 0.01em;
  background-clip: text;
  -webkit-text-fill-color: transparent;
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
  background: rgb(99 138 206 / 16%);
  border-radius: 999px;
}

.kpi-bar-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width 0.6s cubic-bezier(0.22, 0.61, 0.36, 1);
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
