<template>
  <div class="records-panel">
    <!-- 筛选区 -->
    <div class="filter-bar">
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="~"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        size="small"
        style="width: 260px"
        @change="onFilterChange"
      />
      <el-select
        v-model="versionId"
        clearable
        filterable
        size="small"
        placeholder="版本"
        style="width: 140px"
        @change="onFilterChange"
      >
        <el-option
          v-for="v in versionOptions"
          :key="v.version_id"
          :label="v.version_name"
          :value="v.version_id"
        />
      </el-select>
      <el-select
        v-model="branchId"
        clearable
        filterable
        size="small"
        placeholder="分支"
        style="width: 140px"
        :disabled="!versionId"
        @change="onFilterChange"
      >
        <el-option
          v-for="b in branchOptions"
          :key="b.branch_id"
          :label="b.branch_name"
          :value="b.branch_id"
        />
      </el-select>
      <el-select
        v-model="userId"
        clearable
        filterable
        size="small"
        placeholder="抢占人"
        style="width: 150px"
        @change="onFilterChange"
      >
        <el-option
          v-for="u in userOptions"
          :key="u.id"
          :label="
            u.display_name ? `${u.display_name}（${u.username}）` : u.username
          "
          :value="u.id"
        />
      </el-select>
      <el-select
        v-model="status"
        clearable
        size="small"
        placeholder="状态"
        style="width: 120px"
        @change="onFilterChange"
      >
        <el-option label="已抢占" value="reserved" />
        <el-option label="已释放" value="released" />
      </el-select>
      <el-button size="small" text @click="resetFilters">重置</el-button>
    </div>

    <!-- 记录表格 -->
    <el-table v-loading="loading" :data="rows" size="small" border>
      <el-table-column label="日期" prop="date" width="110" />
      <el-table-column label="时段" min-width="160">
        <template #default="{ row }">
          {{ row.template_name }} {{ row.start_time }} – {{ row.end_time }}
        </template>
      </el-table-column>
      <el-table-column
        label="用途"
        prop="purpose"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column label="版本/分支" width="150">
        <template #default="{ row }"
          >{{ row.version_name }} / {{ row.branch_name }}</template
        >
      </el-table-column>
      <el-table-column label="抢占人" prop="user_name" width="110" />
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag
            size="small"
            :type="bookingStatusMeta(row.status).type"
            effect="plain"
          >
            {{ bookingStatusMeta(row.status).text }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="抢占时刻" prop="created_at" width="160" />
      <el-table-column label="操作" width="90" fixed="right" align="center">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'reserved'"
            size="small"
            text
            type="danger"
            @click="handleRelease(row as BookingRow)"
          >
            释放
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        background
        @current-change="load"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import dayjs from "dayjs";
import { getPlan } from "@/api/plan";
import { getUsersAll } from "@/api/branchConfig";
import {
  getSlotBookings,
  releaseBooking,
  type BookingRow
} from "@/api/slotBooking";
// 抢占状态文案/颜色映射唯一来源（页面内禁止复制，含不可达 expired 死分支已删除）
import { bookingStatusMeta } from "@/views/constants";

defineOptions({ name: "SlotRecordsPanel" });

const loading = ref(false);
const rows = ref<BookingRow[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;

const dateRange = ref<[string, string] | null>(null);
const versionId = ref<number | null>(null);
const branchId = ref<number | null>(null);
const userId = ref<number | null>(null);
// 状态筛选与后端值域对齐（expired 已随死枚举清理，过期由前端按日期置灰）
const status = ref<"" | "reserved" | "released">("");

const versionOptions = ref<Awaited<ReturnType<typeof getPlan>>>([]);
const userOptions = ref<Awaited<ReturnType<typeof getUsersAll>>>([]);

const branchOptions = computed(
  () =>
    versionOptions.value.find(v => v.version_id === versionId.value)
      ?.branches ?? []
);

async function load() {
  loading.value = true;
  try {
    const data = await getSlotBookings({
      page: page.value,
      page_size: pageSize,
      date_from: dateRange.value?.[0],
      date_to: dateRange.value?.[1],
      version_id: versionId.value ?? undefined,
      branch_id: branchId.value ?? undefined,
      user_id: userId.value ?? undefined,
      status: status.value || undefined
    });
    rows.value = data.items;
    total.value = data.total;
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false;
  }
}

function onFilterChange() {
  if (versionId.value === null) branchId.value = null;
  page.value = 1;
  load();
}

function resetFilters() {
  dateRange.value = null;
  versionId.value = null;
  branchId.value = null;
  userId.value = null;
  status.value = "";
  page.value = 1;
  load();
}

async function handleRelease(row: BookingRow) {
  let reason = "";
  try {
    const result = await ElMessageBox.prompt(
      `确定释放 ${row.date} ${row.template_name}（${row.start_time}-${row.end_time}）吗？管理员释放他人抢占需填写原因。`,
      "释放确认",
      {
        type: "warning",
        confirmButtonText: "确定释放",
        cancelButtonText: "取消",
        inputPlaceholder: "释放原因（必填）",
        inputValidator: (value: string) =>
          (value ?? "").trim().length > 0 ? true : "请填写释放原因"
      }
    );
    reason = (result.value ?? "").trim();
  } catch {
    return; // 用户取消
  }
  try {
    await releaseBooking(row.id, reason);
    ElMessage.success("已释放");
    load();
  } catch {
    // 拦截器已提示
  }
}

onMounted(async () => {
  // 默认筛选近一个月（前 7 天 ~ 后 30 天）：赋值必须先于首次 load()，
  // 否则首查不带日期条件、表格展示未过滤全量而筛选器却显示着范围（R3-F3）
  const today = dayjs();
  dateRange.value = [
    today.subtract(7, "day").format("YYYY-MM-DD"),
    today.add(30, "day").format("YYYY-MM-DD")
  ];
  load();
  const [plan, users] = await Promise.all([
    getPlan({ date: today.format("YYYY-MM-DD") }).catch(() => []),
    getUsersAll().catch(() => [])
  ]);
  versionOptions.value = plan;
  userOptions.value = users;
});
</script>

<style scoped lang="scss">
.records-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.pager {
  display: flex;
  justify-content: flex-end;
}
</style>
