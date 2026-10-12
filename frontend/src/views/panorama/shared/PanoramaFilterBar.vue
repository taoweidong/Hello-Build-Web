<!-- 调度全景共用筛选栏：版本 / 分支 / 仅看我的 + 布局切换 + 我的抢占 + 刷新 -->
<!-- 配色与样式一律复用 business.scss 的 .biz-* 类与 Element Plus 语义变量（设计文档 §4.1） -->
<template>
  <div class="biz-filter-bar">
    <div class="biz-filter-left">
      <span class="biz-sub">版本</span>
      <el-select
        :model-value="versionId"
        placeholder="全部版本"
        clearable
        size="small"
        style="width: 160px"
        @update:model-value="emit('update:versionId', $event || undefined)"
      >
        <el-option
          v-for="v in versions"
          :key="v.version_id"
          :label="v.version_name"
          :value="v.version_id"
        />
      </el-select>
      <span class="biz-sub">分支</span>
      <el-select
        :model-value="branchIds"
        multiple
        collapse-tags
        collapse-tags-tooltip
        placeholder="全部分支"
        size="small"
        style="width: 220px"
        @update:model-value="emit('update:branchIds', $event)"
      >
        <el-option
          v-for="b in branches"
          :key="b.branch_id"
          :label="b.branch_name"
          :value="b.branch_id"
        />
      </el-select>
      <el-checkbox
        :model-value="scope === 'mine'"
        size="small"
        @update:model-value="emit('update:scope', $event ? 'mine' : 'all')"
      >
        仅看我的
      </el-checkbox>
    </div>
    <div class="biz-filter-left">
      <LayoutSwitcher />
      <el-button size="small" @click="emit('open-my-bookings')"
        >我的抢占</el-button
      >
      <el-button size="small" :loading="loading" @click="emit('refresh')"
        >刷新</el-button
      >
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutSwitcher from "./LayoutSwitcher.vue";

defineProps<{
  versions: Array<{ version_id: number; version_name: string }>;
  branches: Array<{ branch_id: number; branch_name: string }>;
  versionId: number | undefined;
  branchIds: number[];
  scope: "all" | "mine";
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: "update:versionId", value: number | undefined): void;
  (e: "update:branchIds", value: number[]): void;
  (e: "update:scope", value: "all" | "mine"): void;
  (e: "open-my-bookings"): void;
  (e: "refresh"): void;
}>();
</script>
