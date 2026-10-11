<template>
  <el-dialog
    :model-value="modelValue"
    title="策略详情（历史任务）"
    width="520px"
    @update:model-value="value => emit('update:modelValue', value)"
  >
    <div class="past-banner">
      该策略所处时段已早于当前时间，为已完成的历史任务，仅支持查看详情，不可修改或借用。
    </div>
    <el-descriptions :column="2" border size="small">
      <el-descriptions-item label="策略名称" :span="2">
        {{ strategy?.strategy_name }}
      </el-descriptions-item>
      <el-descriptions-item label="来源版本">
        {{ strategy?.version_name }}
      </el-descriptions-item>
      <el-descriptions-item label="分支">
        {{ strategy?.branch_name }}
      </el-descriptions-item>
      <el-descriptions-item label="冒烟模板">
        {{ strategy?.template_name }}
      </el-descriptions-item>
      <el-descriptions-item label="构建时间">
        {{ strategy?.build_start_time }}
      </el-descriptions-item>
      <el-descriptions-item label="推送模式">
        {{ strategy?.push_start_time ? "同步推送" : "正常流程" }}
      </el-descriptions-item>
      <el-descriptions-item label="推送时间">
        {{ strategy?.push_start_time || "结论后推导" }}
      </el-descriptions-item>
    </el-descriptions>

    <template #footer>
      <el-button type="primary" @click="emit('update:modelValue', false)">
        关闭
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// 版本策略全景页 - 已过期历史任务的只读详情弹窗（不支持任何修改/借用操作）
import type { WeeklyStrategy } from "@/api/types";

defineOptions({ name: "WeeklyNewStrategyDetailDialog" });

defineProps<{
  modelValue: boolean;
  strategy: (WeeklyStrategy & { version_name?: string }) | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
}>();
</script>

<style scoped lang="scss">
.past-banner {
  margin-bottom: 12px;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 18px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  border-left: 3px solid var(--el-border-color);
  border-radius: 4px;
}
</style>
