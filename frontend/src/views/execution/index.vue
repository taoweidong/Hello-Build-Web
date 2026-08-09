<script setup lang="ts">
// 今日执行看板
// 设计文档 8.3：统计卡片、五列状态流转、结论录入弹窗（仅 tester）、30s 轮询、PM 仅本版本
import { ref, computed, onMounted, onUnmounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getExecutions, submitConclusion } from "@/api/execution";
import type { RoundItem } from "@/api/types";
import { getCurrentUser, timeToMs, dayjs, formatTime } from "@/utils/business";

defineOptions({ name: "ExecutionIndex" });

const currentUser = getCurrentUser();
const loading = ref(false);
const roundList = ref<RoundItem[]>([]);
const now = ref(Date.now());

// ---- 阶段状态推导（按当前时间与绝对区间比较）----
function stageStatus(phase: {
  start: string;
  end: string;
}): { type: string; label: string } {
  const start = timeToMs(phase.start);
  const end = timeToMs(phase.end);
  const t = now.value;
  if (t < start) return { type: "info", label: "待执行" };
  if (t <= end) return { type: "primary", label: "进行中" };
  return { type: "success", label: "已完成" };
}

// ---- 统计卡片 ----
const stats = computed(() => {
  const total = roundList.value.length;
  const running = roundList.value.filter(r => {
    const build = stageStatus({ start: r.build_start, end: r.build_end });
    const smoke = stageStatus({ start: r.smoke_start, end: r.smoke_end });
    const analysis = stageStatus({
      start: r.analysis_start,
      end: r.analysis_end
    });
    return [build, smoke, analysis].some(s => s.type === "primary");
  }).length;
  const pendingConclusion = roundList.value.filter(
    r => r.conclusion === "pending" && now.value > timeToMs(r.analysis_end)
  ).length;
  const pushSuccess = roundList.value.filter(
    r => r.push_status === "success"
  ).length;
  return { total, running, pendingConclusion, pushSuccess };
});

// 统计卡片配置
const statCards = computed(() => [
  { label: "今日轮次", value: stats.value.total, color: "#3b82f6" },
  { label: "进行中", value: stats.value.running, color: "#8b5cf6" },
  { label: "待录结论", value: stats.value.pendingConclusion, color: "#f59e0b" },
  { label: "推送成功", value: stats.value.pushSuccess, color: "#10b981" }
]);

// ---- 数据加载 ----
async function load() {
  loading.value = true;
  try {
    const today = dayjs().format("YYYY-MM-DD");
    roundList.value = await getExecutions({ date: today });
    now.value = Date.now();
  } finally {
    loading.value = false;
  }
}

// ---- 结论录入弹窗 ----
const conclusionDialog = ref(false);
const conclusionForm = ref({
  roundId: 0 as number | null,
  conclusion: "pass" as string,
  note: ""
});

function openConclusion(round: RoundItem) {
  if (currentUser?.role !== "tester") {
    ElMessage.warning("仅防护网测试人员可录入结论");
    return;
  }
  conclusionForm.value = {
    roundId: round.id,
    conclusion: "pass",
    note: ""
  };
  conclusionDialog.value = true;
}

async function onConclusionSubmit() {
  if (!conclusionForm.value.roundId) return;
  await ElMessageBox.confirm(
    "确认提交该结论？提交后不可重复录入。",
    "提交结论",
    { type: "warning", confirmButtonText: "确认提交", cancelButtonText: "取消" }
  );
  await submitConclusion(conclusionForm.value.roundId as number, {
    conclusion: conclusionForm.value.conclusion,
    note: conclusionForm.value.note || undefined
  });
  conclusionDialog.value = false;
  ElMessage.success("结论已提交");
  load();
}

// ---- 30s 轮询 ----
let timer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  load();
  timer = setInterval(load, 30000);
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
});

// 展示辅助
function phaseRange(r: RoundItem, key: "build" | "smoke" | "analysis") {
  const map = {
    build: [r.build_start, r.build_end],
    smoke: [r.smoke_start, r.smoke_end],
    analysis: [r.analysis_start, r.analysis_end]
  } as Record<string, [string, string]>;
  const [s, e] = map[key];
  return `${formatTime(s, "HH:mm")}-${formatTime(e, "HH:mm")}`;
}

function conclusionTag(r: RoundItem): { type: string; label: string } {
  if (r.conclusion === "pass") return { type: "success", label: "通过" };
  if (r.conclusion === "fail") return { type: "danger", label: "不通过" };
  return { type: "info", label: "待录" };
}

const pushStatusMap: Record<string, { type: string; label: string }> = {
  pending: { type: "info", label: "待推送" },
  running: { type: "primary", label: "推送中" },
  success: { type: "success", label: "推送成功" },
  failed: { type: "danger", label: "推送失败" },
  skipped: { type: "warning", label: "跳过" }
};
</script>

<template>
  <div class="execution-page">
    <!-- 统计卡片 -->
    <div class="stat-cards">
      <div
        v-for="c in statCards"
        :key="c.label"
        class="stat-card"
        :style="{ '--accent': c.color }"
      >
        <div class="stat-value">{{ c.value }}</div>
        <div class="stat-label">{{ c.label }}</div>
      </div>
    </div>

    <!-- 轮次表格 -->
    <div class="table-card" v-loading="loading">
      <div class="table-head">
        <span class="table-title">今日执行轮次</span>
        <el-button size="small" @click="load">刷新</el-button>
      </div>
      <el-table :data="roundList" style="width: 100%">
        <el-table-column prop="strategy_name" label="策略" min-width="160" />
        <el-table-column label="构建" min-width="150">
          <template #default="{ row }">
            <el-tag :type="stageStatus({ start: row.build_start, end: row.build_end }).type" size="small">
              {{ stageStatus({ start: row.build_start, end: row.build_end }).label }}
            </el-tag>
            <span class="phase-time">{{ phaseRange(row, "build") }}</span>
          </template>
        </el-table-column>
        <el-table-column label="冒烟" min-width="150">
          <template #default="{ row }">
            <el-tag :type="stageStatus({ start: row.smoke_start, end: row.smoke_end }).type" size="small">
              {{ stageStatus({ start: row.smoke_start, end: row.smoke_end }).label }}
            </el-tag>
            <span class="phase-time">{{ phaseRange(row, "smoke") }}</span>
          </template>
        </el-table-column>
        <el-table-column label="人工分析" min-width="150">
          <template #default="{ row }">
            <el-tag :type="stageStatus({ start: row.analysis_start, end: row.analysis_end }).type" size="small">
              {{ stageStatus({ start: row.analysis_start, end: row.analysis_end }).label }}
            </el-tag>
            <span class="phase-time">{{ phaseRange(row, "analysis") }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" min-width="140">
          <template #default="{ row }">
            <el-button
              v-if="row.conclusion === 'pending' && currentUser?.role === 'tester'"
              type="primary"
              size="small"
              @click="openConclusion(row)"
            >
              录入结论
            </el-button>
            <el-tag v-else :type="conclusionTag(row).type" size="small">
              {{ conclusionTag(row).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推送" min-width="120">
          <template #default="{ row }">
            <el-tag
              :type="(pushStatusMap[row.push_status] || pushStatusMap.pending).type"
              size="small"
            >
              {{ (pushStatusMap[row.push_status] || pushStatusMap.pending).label }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 结论录入弹窗 -->
    <el-dialog
      v-model="conclusionDialog"
      title="录入人工分析结论"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form label-width="80px">
        <el-form-item label="结论">
          <el-radio-group v-model="conclusionForm.conclusion">
            <el-radio value="pass">通过</el-radio>
            <el-radio value="fail">不通过</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="conclusionForm.note"
            type="textarea"
            :rows="3"
            placeholder="请输入备注（可选）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="conclusionDialog = false">取消</el-button>
        <el-button type="primary" @click="onConclusionSubmit">确认提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.execution-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.stat-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  border-left: 4px solid var(--accent);
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--accent);
}
.stat-label {
  margin-top: 4px;
  color: #909399;
  font-size: 13px;
}
.table-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}
.table-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.table-title {
  color: #303133;
  font-weight: 600;
}
.phase-time {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
</style>