<script setup lang="ts">
// 策略全景页（全角色只读）
// 设计文档 8.4：版本→分支级联筛选、策略卡片网格、点击联动执行历史表格、行展开日志抽屉
import { ref, reactive, computed, onMounted } from "vue";
import { getStrategies, getExecutions, getRoundDetail } from "@/api/panorama";
import type { StrategyItem, RoundItem, ExecutionLogItem } from "@/api/types";
import { dayjs, timeToMs, formatTime } from "@/utils/business";

defineOptions({ name: "PanoramaIndex" });

const loading = ref(false);
const strategies = ref<StrategyItem[]>([]);
const executions = ref<RoundItem[]>([]);
const selectedStrategy = ref<StrategyItem | null>(null);

// ---- 筛选条件 ----
const filter = reactive({
  version_id: undefined as number | undefined,
  branch_id: undefined as number | undefined,
  range: [dayjs().subtract(6, "day").format("YYYY-MM-DD"), dayjs().format("YYYY-MM-DD")] as string[]
});

// 版本/分支选项（从策略数据提取）
const versionOptions = computed(() => {
  const map = new Map<number, { id: number; name: string }>();
  strategies.value.forEach(s => {
    if (!map.has(s.version_id)) {
      map.set(s.version_id, { id: s.version_id, name: s.version_name || "" });
    }
  });
  return Array.from(map.values());
});
const branchOptions = computed(() => {
  if (!filter.version_id) return [];
  return strategies.value
    .filter(s => s.version_id === filter.version_id)
    .map(s => ({ id: s.branch_id, name: s.branch_name }))
    .filter((v, i, a) => a.findIndex(x => x.id === v.id) === i);
});

// 按版本分组：每一行展示一个版本的配置/策略信息，行内卡片横向铺满
const grouped = computed(() => {
  const result: Array<{ version: string; list: StrategyItem[] }> = [];
  const vMap = new Map<string, StrategyItem[]>();
  strategies.value.forEach(s => {
    const version = s.version_name || `版本${s.version_id}`;
    if (!vMap.has(version)) {
      const list: StrategyItem[] = [];
      vMap.set(version, list);
      result.push({ version, list });
    }
    vMap.get(version)!.push(s);
  });
  return result;
});

// ---- 加载策略 ----
async function loadStrategies() {
  loading.value = true;
  try {
    strategies.value = await getStrategies({
      version_id: filter.version_id,
      branch_id: filter.branch_id
    });
  } finally {
    loading.value = false;
  }
}

function onVersionChange() {
  filter.branch_id = undefined;
  loadStrategies();
}
function onBranchChange() {
  loadStrategies();
}

// ---- 联动执行历史 ----
async function selectStrategy(s: StrategyItem) {
  if (selectedStrategy.value?.id === s.id) {
    selectedStrategy.value = null;
    executions.value = [];
    return;
  }
  selectedStrategy.value = s;
  const [from, to] = filter.range;
  executions.value = await getExecutions({
    strategy_id: s.id,
    from,
    to
  });
}

// ---- 执行日志抽屉 ----
const drawerVisible = ref(false);
const drawerLogs = ref<ExecutionLogItem[]>([]);
const drawerRound = ref<RoundItem | null>(null);

async function openLog(round: RoundItem) {
  drawerRound.value = round;
  const detail = await getRoundDetail(round.id);
  drawerLogs.value = detail.logs || [];
  drawerVisible.value = true;
}

// ---- 展示辅助 ----
const pushStatusMap: Record<string, string> = {
  pending: "待推送",
  running: "推送中",
  success: "成功",
  failed: "失败",
  skipped: "跳过"
};
const conclusionMap: Record<string, string> = {
  pending: "待录",
  pass: "通过",
  fail: "不通过"
};

function phaseShort(r: RoundItem, key: "build" | "smoke" | "analysis") {
  const map = {
    build: [r.build_start, r.build_end],
    smoke: [r.smoke_start, r.smoke_end],
    analysis: [r.analysis_start, r.analysis_end]
  } as Record<string, [string, string]>;
  const [s, e] = map[key];
  return `${formatTime(s, "MM-DD HH:mm")} ~ ${formatTime(e, "HH:mm")}`;
}

onMounted(loadStrategies);
</script>

<template>
  <div class="panorama-page">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <span class="filter-title">筛选</span>
      <el-select
        v-model="filter.version_id"
        placeholder="全部版本"
        clearable
        style="width: 160px"
        @change="onVersionChange"
      >
        <el-option v-for="v in versionOptions" :key="v.id" :label="v.name" :value="v.id" />
      </el-select>
      <el-select
        v-model="filter.branch_id"
        placeholder="全部分支"
        clearable
        :disabled="!filter.version_id"
        style="width: 160px"
        @change="onBranchChange"
      >
        <el-option v-for="b in branchOptions" :key="b.id" :label="b.name" :value="b.id" />
      </el-select>
      <el-date-picker
        v-model="filter.range"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        style="width: 260px"
        @change="selectedStrategy && selectStrategy(selectedStrategy)"
      />
      <el-button type="primary" :loading="loading" @click="loadStrategies">查询</el-button>
    </div>

    <!-- ① 策略配置全景区 -->
    <div class="section">
      <div class="section-title">策略配置全景</div>
      <div v-loading="loading" class="strategy-area">
        <!-- 每一行 = 一个版本：左侧版本徽章，右侧该版本各分支策略卡片横向铺满 -->
        <div v-for="g in grouped" :key="g.version" class="version-row">
          <div class="version-side">
            <span class="version-badge">{{ g.version }}</span>
          </div>
          <div class="version-cards">
            <div
              v-for="s in g.list"
              :key="s.id"
              class="strategy-card"
              :class="{ active: selectedStrategy?.id === s.id }"
              @click="selectStrategy(s)"
            >
              <div class="card-name">
                {{ s.name }}
                <span class="card-branch">{{ s.branch_name }}</span>
              </div>
              <div class="card-meta">模板：{{ s.template_name }}</div>
              <div class="card-meta">构建开始：{{ s.build_start_time }}</div>
              <div class="card-meta">
                推送模式：{{ s.push_mode === "sync" ? "同步推送冒烟" : "正常流程推送" }}
              </div>
              <div class="card-meta">
                状态：
                <el-tag :type="s.enabled ? 'success' : 'info'" size="small">
                  {{ s.enabled ? "启用" : "停用" }}
                </el-tag>
              </div>
            </div>
          </div>
        </div>
        <el-empty v-if="!loading && strategies.length === 0" description="暂无策略配置" />
      </div>
    </div>

    <!-- ② 执行实践全景区 -->
    <div class="section">
      <div class="section-title">
        执行实践全文区
        <span v-if="selectedStrategy" class="section-sub">
          —— {{ selectedStrategy.name }}
        </span>
      </div>
      <el-empty
        v-if="!selectedStrategy"
        description="点击上方策略卡片查看其历史执行实践"
      />
      <el-table
        v-else
        :data="executions"
        style="width: 100%"
        @row-click="openLog"
      >
        <el-table-column label="日期" width="120">
          <template #default="{ row }">{{ row.exec_date }}</template>
        </el-table-column>
        <el-table-column label="构建" min-width="170">
          <template #default="{ row }">{{ phaseShort(row, "build") }}</template>
        </el-table-column>
        <el-table-column label="冒烟" min-width="170">
          <template #default="{ row }">{{ phaseShort(row, "smoke") }}</template>
        </el-table-column>
        <el-table-column label="分析" min-width="170">
          <template #default="{ row }">{{ phaseShort(row, "analysis") }}</template>
        </el-table-column>
        <el-table-column label="结论" width="90">
          <template #default="{ row }">
            <el-tag
              :type="row.conclusion === 'pass' ? 'success' : row.conclusion === 'fail' ? 'danger' : 'info'"
              size="small"
            >
              {{ conclusionMap[row.conclusion] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推送" width="90">
          <template #default="{ row }">
            {{ pushStatusMap[row.push_status] || row.push_status }}
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">{{ row.conclusion_note || "-" }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 日志抽屉 -->
    <el-drawer v-model="drawerVisible" title="执行日志" size="420px">
      <template v-if="drawerRound">
        <div class="drawer-round">
          <div>执行日期：{{ drawerRound.exec_date }}</div>
          <div>结论：{{ conclusionMap[drawerRound.conclusion] }}</div>
          <div>推送：{{ pushStatusMap[drawerRound.push_status] }}</div>
        </div>
      </template>
      <el-timeline v-if="drawerLogs.length">
        <el-timeline-item
          v-for="log in drawerLogs"
          :key="log.id"
          :timestamp="formatTime(log.at, 'MM-DD HH:mm:ss')"
        >
          <b>[{{ log.stage }}] {{ log.event }}</b>
          <div v-if="log.detail" class="log-detail">{{ log.detail }}</div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无日志" />
    </el-drawer>
  </div>
</template>

<style scoped>
.panorama-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 16px;
}
.filter-title {
  color: #909399;
  font-size: 13px;
}
.section {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}
.section-title {
  color: #303133;
  font-weight: 600;
  margin-bottom: 12px;
}
.section-sub {
  color: #909399;
  font-weight: 400;
  font-size: 13px;
}
/* 策略区：每行一个版本，纵向堆叠 */
.strategy-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.version-row {
  display: flex;
  align-items: stretch;
  gap: 12px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
}
.version-side {
  flex: 0 0 64px;
  display: flex;
  justify-content: center;
  padding-top: 6px;
}
.version-badge {
  background: #eff6ff;
  color: #3b82f6;
  border: 1px solid #bfdbfe;
  border-radius: 4px;
  padding: 2px 10px;
  font-size: 13px;
  font-weight: 600;
}
/* 行内策略卡片横向铺满：auto-fit 卡片少时自动拉伸，消除右侧空白 */
.version-cards {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px;
}
.card-branch {
  margin-left: 6px;
  color: #909399;
  font-size: 12px;
  font-weight: 400;
  background: #f2f3f5;
  border-radius: 4px;
  padding: 1px 6px;
}
.strategy-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.strategy-card:hover {
  border-color: #3b82f6;
}
.strategy-card.active {
  border-color: #3b82f6;
  box-shadow: 0 0 0 1px #3b82f6;
}
.card-name {
  color: #303133;
  font-weight: 600;
  margin-bottom: 8px;
}
.card-meta {
  color: #909399;
  font-size: 12px;
  line-height: 1.8;
}
.drawer-round {
  color: #909399;
  font-size: 13px;
  line-height: 1.9;
  margin-bottom: 12px;
}
.log-detail {
  color: #909399;
  font-size: 12px;
  margin-top: 2px;
}
</style>