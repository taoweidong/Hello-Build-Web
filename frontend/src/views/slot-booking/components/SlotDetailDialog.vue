<template>
  <el-dialog
    :model-value="modelValue"
    :title="isMine ? '我的抢占详情' : '时段已被抢占'"
    width="440px"
    @update:model-value="value => emit('update:modelValue', value)"
  >
    <div v-if="template && entry?.booking" class="detail-wrap">
      <div class="detail-row">
        <span class="detail-label">日期时段</span>
        <span
          >{{ dateLabel }}（{{ weekLabel }}）{{ template.start_time }} –
          {{ template.end_time }}</span
        >
      </div>
      <div class="detail-row">
        <span class="detail-label">抢占人</span>
        <span :class="{ 'mine-name': isMine }">{{
          entry.booking.user_name
        }}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">用途</span>
        <span>{{ entry.booking.purpose }}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">关联</span>
        <span
          >{{ entry.booking.version_name }} /
          {{ entry.booking.branch_name }}</span
        >
      </div>
      <div class="detail-row">
        <span class="detail-label">抢占时刻</span>
        <span>{{ entry.booking.created_at }}</span>
      </div>
      <el-alert
        v-if="!isMine"
        title="该时段已被他人抢占，如需协调请联系抢占人或管理员"
        type="info"
        :closable="false"
        show-icon
      />
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
      <el-button
        v-if="isMine"
        type="danger"
        plain
        :loading="releasing"
        @click="handleRelease"
      >
        释放该时段
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import dayjs from "dayjs";
import { ElMessageBox } from "element-plus";
import {
  releaseBooking,
  type CalendarDayCell,
  type SlotTemplateItem
} from "@/api/slotBooking";
// 中文星期数组唯一来源（utils/week，页面内禁止手写复制）
import { WEEKDAY_CN_SUN } from "@/utils/week";

defineOptions({ name: "SlotDetailDialog" });

const props = defineProps<{
  modelValue: boolean;
  date: string;
  entry: CalendarDayCell | null;
  template: SlotTemplateItem | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "released"): void;
}>();

const releasing = ref(false);

const isMine = computed(() => props.entry?.booking?.is_mine === true);
const dateLabel = computed(() => dayjs(props.date).format("YYYY年M月D日"));
const weekLabel = computed(() => WEEKDAY_CN_SUN[dayjs(props.date).day()]);

async function handleRelease() {
  if (!props.entry?.booking) return;
  try {
    await ElMessageBox.confirm(
      `确定释放 ${props.date} ${props.template?.start_time}-${props.template?.end_time} 的抢占吗？释放后其他成员可立即抢占该时段。`,
      "释放确认",
      {
        type: "warning",
        confirmButtonText: "确定释放",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return; // 用户取消
  }
  releasing.value = true;
  try {
    await releaseBooking(props.entry.booking.id);
    emit("released"); // 成功提示由父组件统一弹出，避免重复 toast
  } catch {
    // 拦截器已提示
  } finally {
    releasing.value = false;
  }
}
</script>

<style scoped lang="scss">
.detail-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-row {
  display: flex;
  gap: 12px;
  font-size: 13px;
  line-height: 20px;

  .detail-label {
    flex: none;
    width: 64px;
    color: var(--el-text-color-secondary);
  }

  .mine-name {
    color: var(--el-color-primary);
    font-weight: 600;
  }
}
</style>
