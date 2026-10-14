<!-- 示例菜单 · 空态引导 /sample/empty -->
<!-- 定位：占位演示页。空态区只留「一句说明 + 主操作按钮」，辅助文案收进卡片头 -->
<template>
  <div class="biz-page">
    <div class="biz-card biz-card-compact">
      <div class="biz-card-head">
        <span class="biz-card-title">空态引导</span>
        <span class="biz-sub">业务页可在此放主操作与帮助链接</span>
      </div>
      <div class="empty-body">
        <el-empty description="暂无示例数据" :image-size="60">
          <el-button type="primary" size="small" @click="noop">
            新建示例条目
          </el-button>
        </el-empty>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";

defineOptions({ name: "SampleEmpty" });

function noop() {
  ElMessage.info("示例页按钮：未接后端，仅作交互占位");
}
</script>

<style scoped lang="scss">
/* 空态区高度收敛到 200px：留白足够聚焦，又不至于撑出大片空白 */
.empty-body {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}
</style>
