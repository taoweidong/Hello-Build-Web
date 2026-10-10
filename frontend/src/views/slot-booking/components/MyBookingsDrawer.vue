<template>
  <el-drawer
    :model-value="modelValue"
    title="我的抢占"
    size="420px"
    @update:model-value="value => emit('update:modelValue', value)"
    @open="load"
  >
    <div v-loading="loading" class="my-bookings">
      <template v-if="rows.length">
        <div v-for="row in rows" :key="row.id" class="booking-item">
          <div class="item-head">
            <span class="item-date"
              >{{ row.date }}（{{ weekdayLabel(row.date) }}）</span
            >
            <el-tag
              size="small"
              :type="statusTagType(row.status)"
              effect="plain"
            >
              {{ statusLabel(row.status) }}
            </el-tag>
          </div>
          <div class="item-slot">
            {{ row.template_name }} {{ row.start_time }} – {{ row.end_time }}
          </div>
          <div class="item-purpose">{{ row.purpose }}</div>
          <div class="item-meta">
            <span>{{ row.version_name }} / {{ row.branch_name }}</span>
            <span>抢占于 {{ row.created_at }}</span>
          </div>
          <div v-if="row.status === 'reserved'" class="item-actions">
            <el-button
              size="small"
              type="danger"
              plain
              :loading="releasingId === row.id"
              @click="handleRelease(row)"
            >
              释放
            </el-button>
          </div>
          <div
            v-else-if="row.status === 'released' && row.release_reason"
            class="item-reason"
          >
            释放原因：{{ row.release_reason }}
          </div>
        </div>
        <el-button
          v-if="rows.length < total"
          text
          type="primary"
          class="load-more"
          @click="loadMore"
        >
          加载更多（{{ rows.length }}/{{ total }}）
        </el-button>
      </template>
      <el-empty
        v-else-if="!loading"
        description="暂无抢占记录，去月历抢占一个时段吧"
        :image-size="80"
      />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import dayjs from "dayjs";
import {
  getMyBookings,
  releaseBooking,
  type BookingRow
} from "@/api/slotBooking";

defineOptions({ name: "MyBookingsDrawer" });

defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "changed"): void;
}>();

const loading = ref(false);
const rows = ref<BookingRow[]>([]);
const total = ref(0);
const page = ref(1);
const releasingId = ref<number | null>(null);

async function load() {
  loading.value = true;
  page.value = 1;
  try {
    const data = await getMyBookings(1, 20);
    rows.value = data.items;
    total.value = data.total;
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false;
  }
}

async function loadMore() {
  const next = page.value + 1;
  const data = await getMyBookings(next, 20).catch(() => null);
  if (data) {
    page.value = next;
    rows.value = [...rows.value, ...data.items];
  }
}

function weekdayLabel(dateStr: string) {
  const names = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  return names[dayjs(dateStr).day()];
}

function statusLabel(status: BookingRow["status"]) {
  return status === "reserved"
    ? "已抢占"
    : status === "released"
      ? "已释放"
      : "已过期";
}

function statusTagType(status: BookingRow["status"]) {
  return status === "reserved"
    ? "success"
    : status === "released"
      ? "info"
      : "warning";
}

async function handleRelease(row: BookingRow) {
  try {
    await ElMessageBox.confirm(
      `确定释放 ${row.date} ${row.template_name}（${row.start_time}-${row.end_time}）吗？`,
      "释放确认",
      {
        type: "warning",
        confirmButtonText: "确定释放",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return;
  }
  releasingId.value = row.id;
  try {
    await releaseBooking(row.id);
    ElMessage.success("已释放");
    await load();
    emit("changed");
  } catch {
    // 拦截器已提示
  } finally {
    releasingId.value = null;
  }
}
</script>

<style scoped lang="scss">
.my-bookings {
  min-height: 200px;
}

.booking-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;

  .item-head {
    display: flex;
    justify-content: space-between;
    align-items: center;

    .item-date {
      font-weight: 600;
      color: var(--el-text-color-primary);
    }
  }

  .item-slot {
    margin-top: 6px;
    font-size: 13px;
    color: var(--el-text-color-regular);
  }

  .item-purpose {
    margin-top: 4px;
    font-size: 13px;
    color: var(--el-text-color-secondary);
  }

  .item-meta {
    display: flex;
    justify-content: space-between;
    margin-top: 4px;
    font-size: 12px;
    color: var(--el-text-color-placeholder);
  }

  .item-actions {
    margin-top: 8px;
    display: flex;
    justify-content: flex-end;
  }

  .item-reason {
    margin-top: 6px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}

.load-more {
  width: 100%;
}
</style>
