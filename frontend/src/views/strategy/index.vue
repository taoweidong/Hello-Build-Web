<script setup lang="ts">
// 策略配置页（仅 PM，仅本版本分支）
// 设计文档 8.5：表单 + 时间线实时预览 preview 接口 + 冲突不可保存
import { ref, reactive, computed, watch, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import http from "@/api/http";
import {
  getStrategies,
  previewStrategy,
  createStrategy,
  updateStrategy,
  toggleStrategy,
  type StrategyForm,
  type PreviewResult
} from "@/api/strategy";
import { getPlan } from "@/api/plan";
import type { StrategyItem, TemplateItem } from "@/api/types";
import { getCurrentUser, dayjs } from "@/utils/business";
import { STAGE_COLORS } from "@/components/gantt/types";

defineOptions({ name: "StrategyIndex" });

const route = useRoute();
const router = useRouter();
const currentUser = getCurrentUser();

// ---- 本版本信息（PM 绑定版本）----
const boundVersionId = currentUser?.bound_version_id;
const boundVersionName = currentUser?.bound_version_name || "";

// ---- 数据 ----
const loading = ref(false);
const strategyList = ref<StrategyItem[]>([]);
const branchOptions = ref<Array<{ id: number; name: string }>>([]);
const templateOptions = ref<TemplateItem[]>([]);
const preview = ref<PreviewResult | null>(null);

// 默认策略名称前缀
function defaultName(branchName: string, templateName: string) {
  return `${boundVersionName}-${branchName}-${templateName}`;
}

// ---- 表单 ----
const form = reactive<StrategyForm>({
  branch_id: 0,
  template_id: 0,
  name: "",
  build_start_time: "22:00",
  push_mode: "normal",
  enabled: true
});
const editingId = ref<number | null>(null);
const isEditing = computed(() => editingId.value !== null);

// 切换分支/模板时自动生成默认名称（若名称未手工修改）
function onBranchTemplateChange() {
  const b = branchOptions.value.find(x => x.id === form.branch_id);
  const t = templateOptions.value.find(x => x.id === form.template_id);
  if (b && t) {
    form.name = defaultName(b.name, t.name);
  }
}

// ---- 加载 ----
async function load() {
  if (!boundVersionId) return;
  loading.value = true;
  try {
    strategyList.value = await getStrategies({ version_id: boundVersionId });
  } finally {
    loading.value = false;
  }
}

async function loadMeta() {
  // 分支选项：从 /plan 提取 PM 绑定版本的分支
  try {
    const plan = await getPlan({ date: dayjs().format("YYYY-MM-DD") });
    const v = plan.find(item => item.version_id === boundVersionId);
    if (v) {
      branchOptions.value = v.branches.map(b => ({ id: b.branch_id, name: b.branch_name }));
    }
  } catch {
    branchOptions.value = [];
  }
  // 模板列表：优先 /admin/templates，失败降级从现有策略提取
  try {
    templateOptions.value = (await http.get("/admin/templates")) as TemplateItem[];
  } catch {
    const set = new Map<number, TemplateItem>();
    strategyList.value.forEach(s => {
      if (!set.has(s.template_id)) {
        set.set(s.template_id, {
          id: s.template_id,
          name: s.template_name,
          smoke_minutes: 0,
          analysis_minutes: 0
        });
      }
    });
    templateOptions.value = Array.from(set.values());
  }
}

// ---- 实时预览（防抖）----
let previewTimer: ReturnType<typeof setTimeout> | null = null;
function schedulePreview() {
  if (!form.branch_id || !form.template_id || !form.build_start_time) return;
  if (previewTimer) clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, 400);
}
async function runPreview() {
  try {
    preview.value = await previewStrategy({
      ...form,
      build_start_time: form.build_start_time
    });
  } catch {
    preview.value = null;
  }
}
watch(
  () => [form.branch_id, form.template_id, form.build_start_time, form.push_mode],
  schedulePreview
);

// ---- 编辑 ----
function startEdit(s: StrategyItem) {
  editingId.value = s.id;
  form.branch_id = s.branch_id;
  form.template_id = s.template_id;
  form.name = s.name;
  form.build_start_time = s.build_start_time;
  form.push_mode = s.push_mode;
  form.enabled = s.enabled;
  schedulePreview();
}
function startNew() {
  editingId.value = null;
  form.branch_id = branchOptions.value[0]?.id || 0;
  form.template_id = templateOptions.value[0]?.id || 0;
  form.build_start_time = "22:00";
  form.push_mode = "normal";
  form.enabled = true;
  onBranchTemplateChange();
  schedulePreview();
}

// ---- 保存 ----
async function onSave() {
  if (preview.value?.conflict) {
    ElMessageBox.alert(
      preview.value.conflict.message || "存在时间冲突，请调整后重试",
      "策略时间冲突",
      { type: "error", confirmButtonText: "知道了" }
    );
    return;
  }
  await ElMessageBox.confirm(
    "确认保存该策略配置？",
    "保存策略",
    { type: "warning", confirmButtonText: "确认保存", cancelButtonText: "取消" }
  );
  if (isEditing.value) {
    await updateStrategy(editingId.value as number, { ...form });
    ElMessage.success("策略已更新");
  } else {
    await createStrategy({ ...form });
    ElMessage.success("策略已创建");
  }
  await load();
  startNew();
}

// ---- 启停 ----
async function onToggle(s: StrategyItem) {
  await toggleStrategy(s.id, s.enabled);
  ElMessage.success(s.enabled ? "策略已启用" : "策略已停用");
}

// ---- 时间线预览渲染 ----
const previewPhases = computed(() => {
  if (!preview.value?.timeline) return [];
  const tl = preview.value.timeline;
  const list = [
    { stage: "push", label: "推送", t: tl.push },
    { stage: "build", label: "构建", t: tl.build },
    { stage: "smoke", label: "冒烟", t: tl.smoke },
    { stage: "analysis", label: "分析", t: tl.analysis }
  ].filter(x => x.t);
  if (list.length === 0) return [];
  const startMs = list.reduce(
    (min, x) => Math.min(min, new Date(x.t.start).getTime()),
    Infinity
  );
  const endMs = list.reduce(
    (max, x) => Math.max(max, new Date(x.t.end).getTime()),
    -Infinity
  );
  const total = Math.max(endMs - startMs, 1);
  return list.map(x => ({
    stage: x.stage,
    label: x.label,
    start: x.t.start,
    end: x.t.end,
    left: ((new Date(x.t.start).getTime() - startMs) / total) * 100,
    width: (Math.max(new Date(x.t.end).getTime() - new Date(x.t.start).getTime(), 1) / total) * 100,
    color: STAGE_COLORS[x.stage]
  }));
});

function fmtPreview(t: string) {
  return dayjs(new Date(t)).format("MM-DD HH:mm");
}

onMounted(async () => {
  await load();
  await loadMeta();
  // 从 URL query 读取编辑 id（F2 甘特跳转）
  const qid = route.query.id;
  if (qid) {
    const s = strategyList.value.find(x => x.id === Number(qid));
    if (s) startEdit(s);
  }
  if (templateOptions.value.length > 0 && !form.branch_id) {
    startNew();
  }
});
</script>

<template>
  <div class="strategy-page">
    <!-- 上半区：本版本策略列表 -->
    <div class="section">
      <div class="row-head">
        <span class="section-title">本版本策略列表（{{ boundVersionName }}）</span>
        <el-button type="primary" size="small" @click="startNew">新建策略</el-button>
      </div>
      <el-table :data="strategyList" v-loading="loading" style="width: 100%">
        <el-table-column prop="name" label="策略名称" min-width="180" />
        <el-table-column prop="branch_name" label="分支" width="110" />
        <el-table-column prop="template_name" label="模板" width="130" />
        <el-table-column prop="build_start_time" label="构建开始" width="110" />
        <el-table-column label="推送模式" width="130">
          <template #default="{ row }">
            {{ row.push_mode === "sync" ? "同步推送冒烟" : "正常流程推送" }}
          </template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="onToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="startEdit(row)">
              编辑
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 下半区：策略编辑表单 + 时间线预览 -->
    <div class="section">
      <div class="section-title">{{ isEditing ? "编辑策略" : "新建策略" }}</div>
      <el-form :model="form" label-width="110px" class="strategy-form">
        <el-form-item label="策略分支">
          <el-select v-model="form.branch_id" style="width: 240px" @change="onBranchTemplateChange">
            <el-option v-for="b in branchOptions" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="策略模板">
          <el-select v-model="form.template_id" style="width: 240px" @change="onBranchTemplateChange">
            <el-option v-for="t in templateOptions" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="策略名称">
          <el-input v-model="form.name" style="width: 360px" placeholder="策略名称" />
        </el-form-item>
        <el-form-item label="构建开始时间">
          <el-time-picker
            v-model="form.build_start_time"
            value-format="HH:mm"
            format="HH:mm"
            placeholder="每天循环"
            style="width: 160px"
          />
          <span class="form-tip">（每日循环，支持跨天）</span>
        </el-form-item>
        <el-form-item label="推送模式">
          <el-radio-group v-model="form.push_mode">
            <el-radio value="normal">正常流程推送</el-radio>
            <el-radio value="sync">同步推送冒烟</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>

      <!-- 时间线实时预览 -->
      <div class="preview-block">
        <div class="preview-title">时间线实时预览</div>
        <div v-if="previewPhases.length" class="preview-bar">
          <div
            v-for="p in previewPhases"
            :key="p.stage"
            class="preview-phase"
            :style="{ left: p.left + '%', width: p.width + '%', background: p.color }"
            :title="`${p.label} ${fmtPreview(p.start)} ~ ${fmtPreview(p.end)}`"
          >
            <span class="preview-phase-label">{{ p.label }}</span>
          </div>
        </div>
        <div v-else class="preview-empty">填写分支/模板/时间后自动预览</div>
        <div v-if="previewPhases.length" class="preview-legend">
          <span v-for="p in previewPhases" :key="p.stage" class="p-legend-item">
            <i class="p-dot" :style="{ background: p.color }"></i>
            {{ p.label }}：{{ fmtPreview(p.start) }}~{{ fmtPreview(p.end) }}
          </span>
        </div>
        <div v-if="preview?.conflict" class="preview-conflict">
          ⚠ {{ preview.conflict.message || "存在时间冲突" }}
        </div>
      </div>

      <div class="form-actions">
        <el-button
          type="primary"
          :disabled="!!preview?.conflict"
          @click="onSave"
        >
          保存策略
        </el-button>
        <el-button @click="startNew">重置</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.strategy-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.section {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}
.row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-title {
  color: #303133;
  font-weight: 600;
}
.form-tip {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}
.preview-block {
  margin-top: 8px;
  background: #f5f7fa;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px;
}
.preview-title {
  color: #909399;
  font-size: 13px;
  margin-bottom: 10px;
}
.preview-bar {
  position: relative;
  height: 40px;
  background: #eef1f6;
  border-radius: 6px;
  overflow: hidden;
}
.preview-phase {
  position: absolute;
  top: 6px;
  bottom: 6px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 11px;
  overflow: hidden;
  white-space: nowrap;
}
.preview-phase-label {
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
}
.preview-empty {
  color: #909399;
  font-size: 12px;
  padding: 12px 0;
}
.preview-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 10px;
  color: #909399;
  font-size: 12px;
}
.p-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.p-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  display: inline-block;
}
.preview-conflict {
  margin-top: 10px;
  color: #ef4444;
  font-size: 13px;
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.4);
  border-radius: 6px;
  padding: 8px 12px;
}
.form-actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}
</style>