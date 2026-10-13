<!-- 调度全景布局切换器：5 个独立路由互跳，偏好写入 localStorage -->
<!-- 「路由本身即状态」，刷新天然保持；?layout= 仅作跨页临时深链 -->
<template>
  <el-select
    :model-value="currentLayout"
    size="small"
    style="width: 132px"
    @update:model-value="onChange"
  >
    <template #prefix>
      <span class="biz-sub">布局</span>
    </template>
    <el-option
      v-for="item in PANORAMA_LAYOUTS"
      :key="item.layout"
      :label="item.title"
      :value="item.layout"
    />
  </el-select>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { storageLocal } from "@pureadmin/utils";
import { panoramaLayoutKey } from "@/store/constants";
import { isLayoutKey, layoutOfPath, PANORAMA_LAYOUTS } from "./panoramaLayouts";

const route = useRoute();
const router = useRouter();

const currentLayout = computed(() => layoutOfPath(route.path));

onMounted(() => {
  // ?layout= 深链：一次性入口。命中即替换为规范路由并同步偏好；
  // 用 replace 而非 push——深链是入口不是历史节点，避免返回时反复横跳。
  const requested = route.query.layout;
  if (!isLayoutKey(requested) || requested === currentLayout.value) return;
  storageLocal().setItem(panoramaLayoutKey, requested);
  router.replace(`/panorama/${requested}`);
});

function onChange(layout: string) {
  const target = PANORAMA_LAYOUTS.find(l => l.layout === layout);
  if (!target) return;
  storageLocal().setItem(panoramaLayoutKey, layout);
  router.push(target.path);
}
</script>
