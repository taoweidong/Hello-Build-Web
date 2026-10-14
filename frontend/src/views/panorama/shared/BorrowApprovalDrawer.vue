<!-- 待我审批抽屉（场景 D 借出）：借用流列表 + 通过/驳回/复制 -->
<!-- 可见性口径与后端一致（admin 全量 / pm = 自己发起 ∪ 自己审批），前端只渲染后端返回的数据 -->
<template>
  <el-drawer
    :model-value="modelValue"
    title="待我审批的借用"
    size="560px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="approval-list">
      <p v-if="!flows.length && !loading" class="biz-tip">
        暂无待审批的借用申请。
      </p>
      <div v-for="f in flows" :key="f.id" class="approval-item">
        <div class="item-head">
          <span class="item-title">{{ f.title }}</span>
          <el-tag size="small" type="warning" effect="plain">{{
            f.statusText
          }}</el-tag>
        </div>
        <div class="item-sub">{{ f.subtitle }}</div>
        <div class="item-reason">
          原因：{{ (f.raw.type === "borrow" && f.raw.data.reason) || "无" }}
        </div>
        <div class="item-actions">
          <el-button
            size="small"
            text
            type="primary"
            @click="actions.copyText(f)"
            >复制</el-button
          >
          <template v-if="f.permissions.canApprove">
            <el-button size="small" type="primary" @click="actions.approve(f)"
              >通过</el-button
            >
            <el-button
              size="small"
              type="danger"
              plain
              @click="actions.reject(f)"
              >驳回</el-button
            >
          </template>
          <!-- 自己发起的申请：可在此撤回（P2-R1），无需回原页面 -->
          <el-button
            v-else-if="f.permissions.canCancel"
            size="small"
            type="warning"
            plain
            @click="actions.cancelBorrow(f)"
            >撤销申请</el-button
          >
          <span v-else class="biz-tip">等待审批中</span>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { ScheduleEvent } from "../types";
import { usePanorama } from "../context";

defineOptions({ name: "PanoramaBorrowApprovalDrawer" });

const props = defineProps<{
  modelValue: boolean;
  /** 待审批借用事件（由布局层从 data.events 过滤后传入） */
  flows: ScheduleEvent[];
}>();

// 原声明的 handled 事件从未 emit 也无监听方，已删除（R4-F13/F-L2）：
// 审批通过/驳回/撤销走动作总线，成功后总线内部统一 data.refresh()，父级无需再感知
const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
}>();

const { data, actions } = usePanorama();
const loading = computed(() => data.loading);
</script>

<style scoped lang="scss">
.approval-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.approval-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;

  .item-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;

    .item-title {
      font-weight: 600;
      color: var(--el-text-color-primary);
    }
  }

  .item-sub {
    margin-top: 6px;
    font-size: 13px;
    color: var(--el-text-color-regular);
  }

  .item-reason {
    margin-top: 4px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .item-actions {
    margin-top: 8px;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
  }
}
</style>
