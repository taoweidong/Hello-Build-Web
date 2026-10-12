<template>
  <section
    class="cloud-panel wk-panel wk-enter"
    :style="{ animationDelay: '400ms' }"
  >
    <div class="wk-panel-head">
      <div class="wk-panel-title">
        热点标签
        <span class="wk-panel-sub">字号随出现次数增长</span>
      </div>
      <div class="tc-legend">
        <span class="tc-legend-item"
          ><i class="tc-swatch tc-swatch--strategy" />策略</span
        >
        <span class="tc-legend-item"
          ><i class="tc-swatch tc-swatch--template" />模板</span
        >
        <span class="tc-legend-item"
          ><i class="tc-swatch tc-swatch--branch" />分支</span
        >
      </div>
    </div>
    <div class="wk-panel-body cloud-body">
      <p v-if="!tags.length" class="viz-empty">当前筛选下暂无标签</p>
      <div v-else class="tc-cloud">
        <span
          v-for="t in tags"
          :key="`${t.kind}-${t.text}`"
          class="tc-tag"
          :class="`tc-tag--${t.kind}`"
          :style="{ fontSize: `${t.size}px` }"
          :title="`${t.text} · 出现 ${t.count} 次`"
        >
          {{ t.text }}
          <em v-if="t.count > 1" class="tc-count">{{ t.count }}</em>
        </span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// 热点标签云：策略名 / 模板名 / 分支名按出现次数加权，hover 显示次数
import type { TagItem } from "@/utils/weeklyReport";

defineOptions({ name: "WeeklyReportTagCloud" });

defineProps<{ tags: TagItem[] }>();
</script>

<style scoped lang="scss">
.cloud-body {
  padding: 14px 16px;
}

.tc-legend {
  display: flex;
  gap: 10px;
  font-size: 11px;
  color: var(--wk-text-3);
}

.tc-legend-item {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.tc-swatch {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.tc-swatch--strategy {
  background: var(--wk-cyan);
  box-shadow: 0 0 7px -1px rgb(56 189 248 / 85%);
}

.tc-swatch--template {
  background: var(--wk-violet);
  box-shadow: 0 0 7px -1px rgb(167 139 250 / 85%);
}

.tc-swatch--branch {
  background: var(--wk-emerald);
  box-shadow: 0 0 7px -1px rgb(52 211 153 / 85%);
}

.tc-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  align-items: center;
  justify-content: center;
  padding: 6px 0;
}

.tc-tag {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  font-weight: 600;
  line-height: 1.5;
  cursor: default;
  border-radius: 6px;
  transition:
    transform 0.2s,
    text-shadow 0.2s,
    color 0.2s;
}

.tc-tag:hover {
  transform: translateY(-2px) scale(1.06);
}

.tc-tag--strategy {
  color: var(--wk-cyan);

  &:hover {
    text-shadow: 0 0 14px rgb(56 189 248 / 75%);
  }
}

.tc-tag--template {
  color: var(--wk-violet);

  &:hover {
    text-shadow: 0 0 14px rgb(167 139 250 / 75%);
  }
}

.tc-tag--branch {
  color: var(--wk-emerald);

  &:hover {
    text-shadow: 0 0 14px rgb(52 211 153 / 75%);
  }
}

.tc-count {
  padding: 0 4px;
  font-size: 9px;
  font-style: normal;
  font-weight: 700;
  line-height: 14px;
  color: var(--wk-text-3);
  border: 1px solid var(--wk-grid-line-strong);
  border-radius: 999px;
}

.viz-empty {
  margin: auto;
  font-size: 12px;
  color: var(--wk-text-3);
}
</style>
