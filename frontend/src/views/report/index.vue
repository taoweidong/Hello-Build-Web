<script setup lang="ts">
// 验证报告列表页：筛选 / 表格 / 复制链接 / 新建
// 权限：tester/builder 可新建，编辑仅作者，其余角色只读（设计文档 4.2）
import { ref, reactive, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { getReports, type ReportQuery } from "@/api/report";
import { getStrategies } from "@/api/strategy";
import type { ReportItem, StrategyItem } from "@/api/types";
import { getCurrentUser, formatTime } from "@/utils/business";

defineOptions({ name: "ReportIndex" });

const router = useRouter();
const currentUser = getCurrentUser();

// ---- 权限 ----
const canWrite = computed(
  () => currentUser?.role === "tester" || currentUser?.role === "builder"
);
function canEdit(row: ReportItem) {
  return canWrite.value && currentUser?.id === row.created_by_id;
}

// ---- 筛选 ----
const loading = ref(false);
const list = ref<ReportItem[]>([]);
const filter = reactive<ReportQuery>({
  keyword: "",
  status: undefined,
  version_id: undefined,
  strategy_id: undefined
});

// 版本/策略级联选项：从全量策略推导（策略自带版本归属）
const allStrategies = ref<StrategyItem[]>([]);
const versionOptions = computed(() => {
  const map = new Map<number, string>();
  allStrategies.value.forEach(s => {
    if (s.version_id != null && !map.has(s.version_id)) {
      map.set(s.version_id, s.version_name || "");
    }
  });
  return Array.from(map, ([id, name]) => ({ id, name }));
});
const strategyOptions = computed(() =>
  allStrategies.value.filter(s => s.version_id === filter.version_id)
);

function onVersionChange() {
  filter.strategy_id = undefined;
  load();
}

async function load() {
  loading.value = true;
  try {
    list.value = await getReports({ ...filter });
  } finally {
    loading.value = false;
  }
}

// ---- 徽章映射 ----
const conclusionMap: Record<string, { text: string; type: "success" | "danger" | "warning" | "info" }> = {
  pass: { text: "通过", type: "success" },
  fail: { text: "不通过", type: "danger" },
  risk: { text: "有风险", type: "warning" }
};
const statusMap: Record<string, { text: string; type: "info" | "success" }> = {
  draft: { text: "草稿", type: "info" },
  published: { text: "已发布", type: "success" }
};
function conclusionTag(c: string) {
  return conclusionMap[c] || { text: c, type: "info" as const };
}
function statusTag(s: string) {
  return statusMap[s] || { text: s, type: "info" as const };
}

// ---- 操作 ----
// 深链接：hash 路由下浏览器地址即 {origin}/#/report/detail/{id}
const reportLink = (id: number) => `${window.location.origin}/#/report/detail/${id}`;

async function copyLink(row: ReportItem) {
  const url = reportLink(row.id);
  try {
    await navigator.clipboard.writeText(url);
  } catch {
    // 降级：非 HTTPS 或浏览器限制时用临时 textarea 复制
    const ta = document.createElement("textarea");
    ta.value = url;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  ElMessage.success("链接已复制，可直接粘贴分享");
}

function goDetail(row: ReportItem) {
  router.push(`/report/detail/${row.id}`);
}
function goEdit(row: ReportItem) {
  router.push({ path: `/report/detail/${row.id}`, query: { edit: "1" } });
}
function goCreate() {
  router.push("/report/detail/new");
}

onMounted(async () => {
  load();
  try {
    allStrategies.value = await getStrategies();
  } catch {
    allStrategies.value = [];
  }
});
</script>

<template>
  <div class="report-page">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-left">
        <el-select
          v-model="filter.status"
          placeholder="全部状态"
          clearable
          style="width: 130px"
          @change="load"
        >
          <el-option label="草稿" value="draft" />
          <el-option label="已发布" value="published" />
        </el-select>
        <el-select
          v-model="filter.version_id"
          placeholder="全部版本"
          clearable
          style="width: 150px"
          @change="onVersionChange"
        >
          <el-option v-for="v in versionOptions" :key="v.id" :label="v.name" :value="v.id" />
        </el-select>
        <el-select
          v-model="filter.strategy_id"
          placeholder="全部策略"
          clearable
          :disabled="!filter.version_id"
          style="width: 190px"
          @change="load"
        >
          <el-option v-for="s in strategyOptions" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <el-input
          v-model="filter.keyword"
          placeholder="标题 / ID 搜索"
          clearable
          style="width: 180px"
          @keyup.enter="load"
        />
        <el-button type="primary" :loading="loading" @click="load">查询</el-button>
      </div>
      <el-button v-if="canWrite" type="primary" @click="goCreate">新建报告</el-button>
    </div>

    <!-- 报告表格 -->
    <div class="section">
      <el-table :data="list" v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="标题" min-width="220">
          <template #default="{ row }">
            <el-link type="primary" :underline="false" @click="goDetail(row as ReportItem)">
              {{ row.title }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column label="关联策略" min-width="200">
          <template #default="{ row }">
            <template v-if="row.version_name && row.strategy_name">
              {{ row.version_name }} / {{ row.strategy_name }}
            </template>
            <span v-else class="no-link">-</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="90">
          <template #default="{ row }">
            <el-tag :type="conclusionTag(row.conclusion).type" size="small">
              {{ conclusionTag(row.conclusion).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status).type" size="small">
              {{ statusTag(row.status).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by_name" label="作者" width="110" />
        <el-table-column label="更新时间" width="140">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="goDetail(row as ReportItem)">
              查看
            </el-button>
            <el-button type="primary" link size="small" @click="copyLink(row as ReportItem)">
              复制链接
            </el-button>
            <el-button
              v-if="canEdit(row as ReportItem)"
              type="primary"
              link
              size="small"
              @click="goEdit(row as ReportItem)"
            >
              编辑
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && list.length === 0" description="暂无报告" />
    </div>
  </div>
</template>

<style scoped>
.report-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 16px;
}
.filter-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.section {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}
.no-link {
  color: #c0c4cc;
}
</style>