<!-- 示例菜单 · 空态引导 /sample/empty -->
<!-- 定位：占位演示页。展示 el-empty + 辅助说明的空白页骨架 -->
<template>
  <div class="biz-page">
    <div class="biz-card empty-card">
      <el-empty description="暂无示例数据">
        <p class="biz-tip placeholder-tip">
          这是空态引导示例：实际业务页可在此放主操作按钮与帮助链接。
        </p>
        <el-button type="primary" @click="noop">新建示例条目</el-button>
      </el-empty>
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
.empty-card {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
}

.placeholder-tip {
  margin: 0 0 12px;
}
</style>
