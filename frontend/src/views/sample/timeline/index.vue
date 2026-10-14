<!-- 示例菜单 · 时间轴 /sample/timeline -->
<!-- 定位：占位演示页。紧凑单行流水（标题为主信息，时间/补充弱化右置） -->
<!-- type 走 el 语义值，不写死颜色 -->
<template>
  <div class="biz-page">
    <div class="biz-card biz-card-compact">
      <div class="biz-card-head">
        <span class="biz-card-title">示例事件流水</span>
        <span class="biz-sub">共 {{ DEMO_TIMELINE.length }} 条</span>
      </div>
      <!-- 隐藏内置 timestamp（默认独占一行），时间改为行内弱化展示 -->
      <el-timeline class="tl">
        <el-timeline-item
          v-for="item in DEMO_TIMELINE"
          :key="item.time"
          :type="item.type"
          hide-timestamp
        >
          <div class="tl-row">
            <span class="tl-title">{{ item.title }}</span>
            <span class="tl-note">{{ item.note }}</span>
            <span class="tl-time">{{ item.time }}</span>
          </div>
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
/* 收紧 el-timeline 默认的行距与左侧留白，条目压成单行 */
.tl {
  padding-left: 2px;

  :deep(.el-timeline-item) {
    padding-bottom: 8px;
  }

  :deep(.el-timeline-item__wrapper) {
    padding-left: 18px;
  }
}

.tl-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
}

.tl-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.tl-note {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.tl-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  white-space: nowrap;
}
</style>
