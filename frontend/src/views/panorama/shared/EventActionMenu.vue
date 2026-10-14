<!-- 行内操作组（S4 分组看板 / S5 时间轴流水共用）
     前 INLINE_LIMIT 个操作常驻行内，其余收进「更多」下拉：
     一行并排 9~10 个按钮会把标题/状态挤没，主要信息反被操作淹没 -->
<template>
  <span class="action-group">
    <el-button
      v-for="a in inlineActions"
      :key="a.key"
      size="small"
      text
      :type="a.type"
      @click="a.run()"
    >
      {{ a.label }}
    </el-button>
    <el-dropdown v-if="overflowActions.length" trigger="click">
      <el-button size="small" text>
        更多<el-icon class="more-arrow"><ArrowDown /></el-icon>
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="a in overflowActions"
            :key="a.key"
            :class="{
              'action-danger': a.type === 'danger',
              'action-warning': a.type === 'warning'
            }"
            @click="a.run()"
          >
            {{ a.label }}
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import ArrowDown from "~icons/ep/arrow-down";
import type { EventAction } from "./eventActions";

/** 行内常驻操作数：超过即收进下拉（与 S1 待办队列保持同一上限口径） */
const INLINE_LIMIT = 2;

const props = defineProps<{
  actions: EventAction[];
}>();

const inlineActions = computed(() => props.actions.slice(0, INLINE_LIMIT));
const overflowActions = computed(() => props.actions.slice(INLINE_LIMIT));
</script>

<style scoped lang="scss">
.action-group {
  display: flex;
  flex: none;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.more-arrow {
  margin-left: 2px;
}

/* 下拉菜单 teleport 到 body，但 scoped 属性仍随本组件 vnode 附着，选择器可命中 */
.action-danger {
  color: var(--el-color-danger);
}

.action-warning {
  color: var(--el-color-warning);
}
</style>
