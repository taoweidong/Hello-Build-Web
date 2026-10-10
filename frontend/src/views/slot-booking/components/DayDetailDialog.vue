<template>
  <el-dialog
    :model-value="modelValue"
    :title="`${dateLabel} 全部时段`"
    width="560px"
    @update:model-value="value => emit('update:modelValue', value)"
  >
    <div class="day-detail-list">
      <div
        v-for="entry in entries"
        :key="entry.template_id"
        class="detail-card"
        :class="{ reserved: entry.status === 'reserved' }"
      >
        <div class="card-head">
          <span
            class="card-color"
            :style="{ background: templates[entry.template_id]?.color }"
          />
          <span class="card-name">{{
            templates[entry.template_id]?.name ?? "未知时段"
          }}</span>
          <span class="card-time">
            {{ templates[entry.template_id]?.start_time }} –
            {{ templates[entry.template_id]?.end_time }}
          </span>
          <el-tag
            size="small"
            :type="entry.status === 'reserved' ? 'info' : 'success'"
            effect="plain"
          >
            {{ entry.status === "reserved" ? "已抢占" : "空闲" }}
          </el-tag>
        </div>
        <div v-if="entry.booking" class="card-booking">
          <span
            >{{ entry.booking.user_name }} · {{ entry.booking.purpose }}</span
          >
          <span class="card-ref"
            >{{ entry.booking.version_name }} /
            {{ entry.booking.branch_name }}</span
          >
        </div>
        <div class="card-actions">
          <el-button
            v-if="entry.status === 'reserved' && entry.booking?.is_mine"
            size="small"
            type="danger"
            plain
            @click="emit('chip-click', entry)"
          >
            查看并释放
          </el-button>
          <el-button
            v-else-if="
              entry.status === 'available' &&
              date >= today &&
              date <= horizonEnd
            "
            size="small"
            type="primary"
            @click="emit('chip-click', entry)"
          >
            去抢占
          </el-button>
        </div>
      </div>
      <el-empty
        v-if="!entries.length"
        description="当日无可用时段"
        :image-size="60"
      />
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from "vue";
import dayjs from "dayjs";
import type { CalendarDayCell, SlotTemplateItem } from "@/api/slotBooking";

defineOptions({ name: "SlotDayDetailDialog" });

const props = defineProps<{
  modelValue: boolean;
  date: string;
  entries: CalendarDayCell[];
  templates: Record<number, SlotTemplateItem>;
  today: string;
  horizonEnd: string;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "chip-click", entry: CalendarDayCell): void;
}>();

const dateLabel = computed(() => dayjs(props.date).format("M月D日"));
</script>

<style scoped lang="scss">
.day-detail-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 60vh;
  overflow-y: auto;
}

.detail-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;

  &.reserved {
    background: var(--el-fill-color-lighter);
  }
}

.card-head {
  display: flex;
  align-items: center;
  gap: 8px;

  .card-color {
    width: 10px;
    height: 10px;
    border-radius: 3px;
  }

  .card-name {
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  .card-time {
    flex: 1;
    font-size: 13px;
    color: var(--el-text-color-secondary);
  }
}

.card-booking {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);

  .card-ref {
    color: var(--el-text-color-secondary);
    white-space: nowrap;
  }
}

.card-actions {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
}
</style>
