<!-- 示例菜单 · 概览卡片 /sample/overview -->
<!-- 定位：占位演示页。展示 .biz-stat-grid 统计卡 + .biz-card/.biz-clickable 功能卡网格 -->
<!-- 配色全部走 Element Plus 语义变量，深浅色自动适配；不接后端接口 -->
<template>
  <div class="biz-page">
    <div class="biz-stat-grid">
      <div v-for="s in DEMO_STATS" :key="s.label" class="biz-card stat-card">
        <div class="stat-label">{{ s.label }}</div>
        <div class="stat-value">{{ s.value }}</div>
        <div class="biz-tip">{{ s.hint }}</div>
      </div>
    </div>

    <div class="biz-card">
      <div class="biz-card-head">
        <span class="biz-card-title">功能占位卡片</span>
        <span class="biz-sub">共 {{ DEMO_FEATURES.length }} 项</span>
      </div>
      <div class="feature-grid">
        <div
          v-for="f in DEMO_FEATURES"
          :key="f.title"
          class="biz-card biz-clickable feature-card"
          tabindex="0"
          :aria-label="f.title"
        >
          <div class="feature-title">{{ f.title }}</div>
          <div class="biz-sub">{{ f.desc }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { DEMO_FEATURES, DEMO_STATS } from "../demoData";

defineOptions({ name: "SampleOverview" });
</script>

<style scoped lang="scss">
.stat-card {
  .stat-label {
    font-size: 13px;
    color: var(--el-text-color-secondary);
  }

  .stat-value {
    margin-top: 4px;
    font-size: 24px;
    font-weight: 500;
    color: var(--el-text-color-primary);
  }
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.feature-card {
  .feature-title {
    margin-bottom: 6px;
    font-size: 14px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }
}
</style>
