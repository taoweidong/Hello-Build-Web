<!-- 示例菜单 · 概览卡片 /sample/overview -->
<!-- 定位：占位演示页。紧凑 KPI 网格（数字为主、补充信息弱化）+ 轻量功能卡网格 -->
<!-- 配色全部走 Element Plus 语义变量，深浅色自动适配；不接后端接口 -->
<template>
  <div class="biz-page">
    <div class="biz-stat-grid">
      <div
        v-for="s in DEMO_STATS"
        :key="s.label"
        class="biz-card biz-card-compact stat-card"
      >
        <div class="stat-label">{{ s.label }}</div>
        <div class="stat-value">{{ s.value }}</div>
        <div class="stat-hint">{{ s.hint }}</div>
      </div>
    </div>

    <div class="biz-card biz-card-compact">
      <div class="biz-card-head">
        <span class="biz-card-title">功能占位卡片</span>
        <span class="biz-sub">共 {{ DEMO_FEATURES.length }} 项</span>
      </div>
      <div class="feature-grid">
        <div
          v-for="f in DEMO_FEATURES"
          :key="f.title"
          class="feature-card biz-clickable"
          tabindex="0"
          :aria-label="f.title"
        >
          <div class="feature-title">{{ f.title }}</div>
          <div class="feature-desc">{{ f.desc }}</div>
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
/* 统计卡：标签/补充信息弱化（12px 次级色），数字放大为主信息 */
.stat-card {
  .stat-label {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .stat-value {
    margin-top: 2px;
    font-size: 22px;
    font-weight: 600;
    line-height: 1.2;
    color: var(--el-text-color-primary);
  }

  .stat-hint {
    margin-top: 2px;
    font-size: 12px;
    color: var(--el-text-color-placeholder);
  }
}

/* 功能卡用轻量描边替代嵌套 .biz-card，避免卡片套卡片的边框噪音 */
.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.feature-card {
  padding: 10px 12px;
  border: 1px solid var(--biz-card-border);
  border-radius: 6px;

  .feature-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  .feature-desc {
    margin-top: 2px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}
</style>
