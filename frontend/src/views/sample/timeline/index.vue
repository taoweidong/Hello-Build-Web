<!-- 示例菜单 · 时间轴 /sample/timeline -->
<!-- 定位：占位演示页。展示 el-timeline 纵向流水（type 走 el 语义值，不写死颜色） -->
<template>
  <div class="biz-page">
    <div class="biz-card">
      <div class="biz-card-head">
        <span class="biz-card-title">示例事件流水</span>
        <span class="biz-sub">共 {{ DEMO_TIMELINE.length }} 条</span>
      </div>
      <el-timeline>
        <el-timeline-item
          v-for="item in DEMO_TIMELINE"
          :key="item.time"
          :timestamp="item.time"
          :type="item.type"
        >
          <div class="item-title">{{ item.title }}</div>
          <div class="biz-sub">{{ item.note }}</div>
        </el-timeline-item>
      </el-timeline>
    </div>
  </div>
</template>

<script setup lang="ts">
import { DEMO_TIMELINE } from "../demoData";

defineOptions({ name: "SampleTimeline" });
</script>

<style scoped lang="scss">
.item-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}
</style>
