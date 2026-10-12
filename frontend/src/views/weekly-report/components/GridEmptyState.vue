<template>
  <div class="grid-empty">
    <div class="ge-badge">
      <IconifyIconOffline :icon="icon" />
    </div>
    <p class="ge-title">{{ title }}</p>
    <p class="ge-hint">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
// 调度网格空态（三种：无数据 / 无分支 / 筛选无匹配）
defineOptions({ name: "WeeklyReportGridEmpty" });

defineProps<{
  icon: unknown;
  title: string;
  hint: string;
}>();
</script>

<style scoped lang="scss">
.grid-empty {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
}

.ge-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  font-size: 26px;
  color: var(--el-text-color-placeholder);
  background: var(--el-fill-color-light);
  border: 1px dashed var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}

.ge-title {
  margin: 4px 0 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.ge-hint {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
