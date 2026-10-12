<template>
  <section
    class="load-panel wk-panel wk-enter"
    :style="{ animationDelay: '240ms' }"
  >
    <div class="wk-panel-head">
      <div class="wk-panel-title">
        分支负载
        <span class="wk-panel-sub">按任务数排序 · 实心构建 / 淡段推送</span>
      </div>
    </div>
    <div class="wk-panel-body load-body">
      <p v-if="!rows.length" class="viz-empty">当前筛选下暂无分支负载数据</p>
      <div v-for="(r, i) in rows" :key="r.branch_id" class="bl-row">
        <span class="bl-name" :title="r.branch_name">
          <i class="wk-dot" :style="{ background: r.color, color: r.color }" />
          <span class="bl-name-text">{{ r.branch_name }}</span>
        </span>
        <span class="bl-count">
          <b>{{ r.total }}</b> 项
          <em v-if="r.push">含推送 {{ r.push }}</em>
        </span>
        <div
          class="bl-bar"
          :title="`${r.branch_name}：构建 ${r.build} · 推送 ${r.push}`"
        >
          <div
            class="bl-fill"
            :style="{
              width: `${(r.total / maxTotal) * 100}%`,
              color: r.color,
              background: `linear-gradient(90deg, ${hexToRgba(r.color, 0.55)}, ${r.color})`,
              animationDelay: `${i * 70}ms`
            }"
          >
            <span
              v-if="r.push"
              class="bl-seg-push"
              :style="{ width: `${(r.push / r.total) * 100}%` }"
            />
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// 分支负载面板：堆叠进度条（构建实心 + 推送淡段），宽度按最大分支归一
import { computed } from "vue";
import { hexToRgba } from "@/utils/color";
import type { BranchLoadRow } from "@/utils/weeklyReport";

defineOptions({ name: "WeeklyReportBranchLoad" });

const props = defineProps<{ rows: BranchLoadRow[] }>();

const maxTotal = computed(
  () => props.rows.reduce((m, r) => Math.max(m, r.total), 0) || 1
);
</script>

<style scoped lang="scss">
.load-body {
  gap: 12px;
  justify-content: center;
}

.bl-row {
  display: grid;
  grid-template-columns: minmax(88px, 1.1fr) auto;
  gap: 4px 12px;
  align-items: center;
}

.bl-name {
  display: flex;
  gap: 7px;
  align-items: center;
  min-width: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--wk-text-1);
}

.bl-name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bl-count {
  font-size: 11px;
  color: var(--wk-text-3);

  b {
    font-size: 13px;
    font-variant-numeric: tabular-nums;
    color: var(--wk-text-1);
  }

  em {
    margin-left: 6px;
    font-style: normal;
    color: var(--wk-text-3);
  }
}

.bl-bar {
  grid-column: 1 / 3;
  height: 8px;
  overflow: hidden;
  background: rgb(99 138 206 / 12%);
  border-radius: 999px;
}

.bl-fill {
  position: relative;
  height: 100%;
  border-radius: 999px;
  box-shadow: 0 0 12px -2px currentcolor;
  transform-origin: left center;
  transition: width 0.5s cubic-bezier(0.22, 0.61, 0.36, 1);
  animation: wk-bar-grow 0.7s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}

/* 推送段：填充右侧的斜纹淡段 */
.bl-seg-push {
  position: absolute;
  inset: 0 0 0 auto;
  height: 100%;
  background-image: repeating-linear-gradient(
    45deg,
    rgb(255 255 255 / 55%) 0 3px,
    transparent 3px 6px
  );
  border-left: 1px dashed rgb(255 255 255 / 65%);
}

.viz-empty {
  margin: auto;
  font-size: 12px;
  color: var(--wk-text-3);
}
</style>
