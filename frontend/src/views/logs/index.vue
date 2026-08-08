<script setup lang="ts">
// 日志中心：执行日志 / 变更日志 / 管理操作（仅 admin）/ 登录安全（仅 admin）
// 设计文档 8.7：统一表格 + 时间范围筛选，Tab 按角色裁剪
import { ref, reactive, onMounted } from "vue";
import { logsApi } from "@/api/logs";
import { getPlan } from "@/api/plan";
import { getCurrentUser, dayjs, formatTime } from "@/utils/business";

defineOptions({ name: "LogsIndex" });

const currentUser = getCurrentUser();
const isAdmin = currentUser?.role === "admin";

const activeTab = ref("execution");

// 时间范围筛选（变更/管理/安全共用）
const range = ref<string[]>([
  dayjs().subtract(6, "day").format("YYYY-MM-DD"),
  dayjs().format("YYYY-MM-DD")
]);

// ---- Tab1 执行日志筛选 ----
const execFilter = reactive({
  date: dayjs().format("YYYY-MM-DD"),
  version_id: undefined as number | undefined,
  branch_id: undefined as number | undefined
});
const versionOptions = ref<Array<{ id: number; name: string; branches: Array<{ id: number; name: string }> }>>(
  []
);
const branchOptions = ref<Array<{ id: number; name: string }>>([]);

// ---- 数据 ----
const execLogs = ref([]);
const changeLogs = ref([]);
const opLogs = ref([]);
const securityLogs = ref([]);
const loading = ref(false);

async function loadVersionOptions() {
  try {
    const plan = await getPlan({ date: dayjs().format("YYYY-MM-DD") });
    versionOptions.value = plan.map(v => ({
      id: v.version_id,
      name: v.version_name,
      branches: v.branches.map(b => ({ id: b.branch_id, name: b.branch_name }))
    }));
  } catch {
    versionOptions.value = [];
  }
}

function onVersionChange() {
  execFilter.branch_id = undefined;
  const v = versionOptions.value.find(x => x.id === execFilter.version_id);
  branchOptions.value = v ? v.branches : [];
}

async function loadExec() {
  loading.value = true;
  try {
    execLogs.value = await logsApi.execution({
      date: execFilter.date,
      version_id: execFilter.version_id,
      branch_id: execFilter.branch_id
    });
  } finally {
    loading.value = false;
  }
}

async function loadChanges() {
  loading.value = true;
  try {
    changeLogs.value = await logsApi.changes({
      from: range.value[0],
      to: range.value[1]
    });
  } finally {
    loading.value = false;
  }
}

async function loadOps() {
  if (!isAdmin) return;
  opLogs.value = await logsApi.operations({
    from: range.value[0],
    to: range.value[1]
  });
}

async function loadSecurity() {
  if (!isAdmin) return;
  securityLogs.value = await logsApi.security({
    from: range.value[0],
    to: range.value[1]
  });
}

function onTabChange(name: string) {
  if (name === "execution") loadExec();
  else if (name === "changes") loadChanges();
  else if (name === "operations") loadOps();
  else if (name === "security") loadSecurity();
}

onMounted(async () => {
  await loadVersionOptions();
  loadExec();
});
</script>

<template>
  <div class="logs-page">
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <!-- Tab1 执行日志 -->
      <el-tab-pane label="执行日志" name="execution">
        <div class="filter-bar">
          <el-date-picker
            v-model="execFilter.date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            :clearable="false"
          />
          <el-select
            v-model="execFilter.version_id"
            placeholder="全部版本"
            clearable
            style="width: 150px"
            @change="onVersionChange"
          >
            <el-option v-for="v in versionOptions" :key="v.id" :label="v.name" :value="v.id" />
          </el-select>
          <el-select
            v-model="execFilter.branch_id"
            placeholder="全部分支"
            clearable
            :disabled="!execFilter.version_id"
            style="width: 150px"
          >
            <el-option v-for="b in branchOptions" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
          <el-button type="primary" :loading="loading" @click="loadExec">查询</el-button>
        </div>
        <el-table :data="execLogs" v-loading="loading" style="width: 100%">
          <el-table-column prop="stage" label="阶段" width="110" />
          <el-table-column prop="event" label="事件" min-width="160" />
          <el-table-column prop="detail" label="详情" min-width="220" />
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.at, "MM-DD HH:mm:ss") }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab2 变更日志 -->
      <el-tab-pane label="变更日志" name="changes">
        <div class="filter-bar">
          <el-date-picker
            v-model="range"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            style="width: 260px"
          />
          <el-button type="primary" :loading="loading" @click="loadChanges">查询</el-button>
        </div>
        <el-table :data="changeLogs" v-loading="loading" style="width: 100%">
          <el-table-column prop="operator" label="操作人" width="120" />
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.at, "MM-DD HH:mm:ss") }}</template>
          </el-table-column>
          <el-table-column prop="strategy_name" label="策略" min-width="160" />
          <el-table-column prop="field" label="字段" width="110" />
          <el-table-column label="变更内容" min-width="220">
            <template #default="{ row }">
              <del class="old">{{ row.old_value }}</del>
              <span class="arrow">→</span>
              <span class="new">{{ row.new_value }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab3 管理操作（仅管理员） -->
      <el-tab-pane v-if="isAdmin" label="管理操作" name="operations">
        <div class="filter-bar">
          <el-date-picker
            v-model="range"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            style="width: 260px"
          />
          <el-button type="primary" @click="loadOps">查询</el-button>
        </div>
        <el-table :data="opLogs" style="width: 100%">
          <el-table-column prop="operator" label="操作人" width="120" />
          <el-table-column prop="action" label="操作" width="140" />
          <el-table-column prop="target_type" label="目标类型" width="120" />
          <el-table-column prop="detail" label="详情" min-width="240" />
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.at, "MM-DD HH:mm:ss") }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab4 登录安全（仅管理员） -->
      <el-tab-pane v-if="isAdmin" label="登录安全" name="security">
        <div class="filter-bar">
          <el-date-picker
            v-model="range"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            style="width: 260px"
          />
          <el-button type="primary" @click="loadSecurity">查询</el-button>
        </div>
        <el-table :data="securityLogs" style="width: 100%">
          <el-table-column prop="username" label="用户" width="140" />
          <el-table-column prop="event" label="事件" min-width="140" />
          <el-table-column prop="ip" label="IP" width="140" />
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.at, "MM-DD HH:mm:ss") }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.logs-page {
  background: #101624;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 16px;
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.old {
  color: #ef4444;
}
.new {
  color: #10b981;
}
.arrow {
  color: #64748b;
  margin: 0 6px;
}
</style>