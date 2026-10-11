<script setup lang="ts">
// 验证报告列表页：筛选 / 表格 / 复制链接 / 新建
// 权限：tester/builder 可新建，编辑仅作者，其余角色只读（设计文档 4.2）
import { ref, reactive, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { getReportRevisions, getReports, type ReportQuery } from "@/api/report";
import { getStrategies } from "@/api/strategy";
import type { ReportItem, ReportRevisionItem, StrategyItem } from "@/api/types";
import { getCurrentUser, formatTime } from "@/utils/business";
import { reportConclusionMeta, reportStatusMeta } from "@/views/constants";

defineOptions({ name: "ReportIndex" });

const router = useRouter();
const currentUser = getCurrentUser();

// ---- 权限 ----
const canWrite = computed(
  () => currentUser?.role === "tester" || currentUser?.role === "builder"
);
function canEdit(row: ReportItem) {
  // 发布后仍可编辑（后端锁定最终结论字段），仅作者可编辑
  return canWrite.value && currentUser?.username === row.created_by_username;
}

// ---- 筛选 ----
const loading = ref(false);
const list = ref<ReportItem[]>([]);
const filter = reactive<ReportQuery>({
  keyword: "",
  status: undefined,
  version_name: undefined,
  strategy_name: undefined
});

// 版本/策略级联选项：从全量策略推导（报告存文本快照，过滤按名称，与后端 FilterSet 对齐）
const allStrategies = ref<StrategyItem[]>([]);
const versionOptions = computed(() => {
  const names = new Set<string>();
  allStrategies.value.forEach(s => {
    if (s.version_name) names.add(s.version_name);
  });
  return Array.from(names, name => ({ name }));
});
const strategyOptions = computed(() =>
  allStrategies.value.filter(s => s.version_name === filter.version_name)
);

function onVersionChange() {
  filter.strategy_name = undefined;
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

// ---- 徽章映射（共享常量，与详情页一致）----
function conclusionTag(c: string) {
  return reportConclusionMeta(c);
}
function statusTag(s: string) {
  return reportStatusMeta(s);
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

// ---- 修改记录弹窗 ----
const revisionsVisible = ref(false);
const revisionsLoading = ref(false);
const revisionsList = ref<ReportRevisionItem[]>([]);
const revisionTagMap: Record<string, "info" | "warning" | "success"> = {
  create: "info",
  update: "warning",
  publish: "success"
};
function revisionTag(r: ReportRevisionItem) {
  return revisionTagMap[r.action] || "info";
}
async function viewRevisions(row: ReportItem) {
  revisionsVisible.value = true;
  revisionsLoading.value = true;
  revisionsList.value = [];
  try {
    revisionsList.value = await getReportRevisions(row.id);
  } catch {
    ElMessage.error("修改记录加载失败");
  } finally {
    revisionsLoading.value = false;
  }
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
  <div class="report-page biz-page">
    <!-- 筛选栏 -->
    <div class="biz-filter-bar">
      <div class="biz-filter-left">
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
          v-model="filter.version_name"
          placeholder="全部版本"
          clearable
          style="width: 150px"
          @change="onVersionChange"
        >
          <el-option v-for="v in versionOptions" :key="v.name" :label="v.name" :value="v.name" />
        </el-select>
        <el-select
          v-model="filter.strategy_name"
          placeholder="全部策略"
          clearable
          :disabled="!filter.version_name"
          style="width: 190px"
          @change="load"
        >
          <el-option v-for="s in strategyOptions" :key="s.name" :label="s.name" :value="s.name" />
        </el-select>
        <el-input
          v-model="filter.keyword"
          placeholder="标题 / 版本 / 策略搜索"
          clearable
          style="width: 180px"
          @keyup.enter="load"
        />
        <el-button type="primary" :loading="loading" @click="load">查询</el-button>
      </div>
      <el-button v-if="canWrite" type="primary" @click="goCreate">新建报告</el-button>
    </div>

    <!-- 报告表格 -->
    <div class="section biz-card">
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
        <el-table-column prop="created_by_username" label="作者" width="110" />
        <el-table-column label="更新时间" width="140">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
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
            <el-button type="warning" link size="small" @click="viewRevisions(row as ReportItem)">
              修改记录
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && list.length === 0" description="暂无报告" />
    </div>

    <!-- 修改记录弹窗：时间倒序，由近及远，含创建/修改/发布留痕 -->
    <el-dialog v-model="revisionsVisible" title="修改记录" width="880px" append-to-body>
      <el-table
        :data="revisionsList"
        v-loading="revisionsLoading"
        max-height="420"
        style="width: 100%"
      >
        <el-table-column label="操作时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="operator_username" label="修改人" width="110" />
        <el-table-column label="操作内容" min-width="150">
          <template #default="{ row }">
            <el-tag :type="revisionTag(row as ReportRevisionItem)" size="small">
              {{ row.action_label }}
            </el-tag>
            <span v-if="row.field_name" style="margin-left: 6px">{{ row.field_name }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="before_value"
          label="修改前内容"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column
          prop="after_value"
          label="修改后内容"
          min-width="160"
          show-overflow-tooltip
        />
        <template #empty>
          <el-empty description="暂无修改记录" />
        </template>
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 页面容器 / 筛选栏 / 卡片容器复用全局 .biz-page / .biz-filter-bar / .biz-card */
.no-link {
  color: var(--el-text-color-placeholder);
}
</style>