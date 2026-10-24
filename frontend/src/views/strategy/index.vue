<script setup lang="ts">
// 策略配置页（仅 PM，仅本版本分支）
// 设计文档 8.5：表单 + 时间线实时预览 preview 接口 + 冲突不可保存
import { ref, reactive, computed, watch, onMounted } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { adminApi } from "@/api/admin";
import {
  getStrategies,
  createStrategy,
  updateStrategy,
  toggleStrategy,
  type StrategyForm
} from "@/api/strategy";
import { useStrategyPreview } from "@/composables/useStrategyPreview";
import { getPlan } from "@/api/plan";
import type { StrategyItem, TemplateItem } from "@/api/types";
import { getCurrentUser, dayjs, parseTime, timeToMs } from "@/utils/business";
// 推送模式文案唯一来源（views/constants，页面内禁止复制措辞）
import { pushModeMeta } from "@/views/constants";
import { STAGE_COLORS } from "@/components/gantt/types";

defineOptions({ name: "StrategyIndex" });

const route = useRoute();
const currentUser = getCurrentUser();

// ---- 本版本信息（PM 绑定版本）----
const boundVersionId = currentUser?.bound_version_id;
const boundVersionName = currentUser?.bound_version_name || "";

// ---- 数据 ----
const loading = ref(false);
const strategyList = ref<StrategyItem[]>([]);
const branchOptions = ref<Array<{ id: number; name: string }>>([]);
const templateOptions = ref<TemplateItem[]>([]);

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
  push_start_time: "",
  push_mode: "normal",
  enabled: true
});
const editingId = ref<number | null>(null);
const isEditing = computed(() => editingId.value !== null);

// ---- 实时预览（防抖 + 过期响应守卫，composable 共用实现）----
// 编辑态透传 id，预览接口据此排除被编辑策略自身，避免原时间未变时误报自冲突
const {
  preview,
  schedule: schedulePreview,
  reset: resetPreview
} = useStrategyPreview(() =>
  form.branch_id && form.template_id
    ? { ...form, id: editingId.value ?? undefined }
    : null
);

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
  } catch {
    strategyList.value = []; // 失败已由拦截器提示，清空避免旧数据误导
  } finally {
    loading.value = false;
  }
}

async function loadMeta() {
  // 分支选项（/plan 提取 PM 绑定版本的分支）与模板列表相互独立，并行拉取
  // 省一档首屏 RTT（R6-F15）；allSettled 保持两者各自独立的降级口径
  const [planRes, templatesRes] = await Promise.allSettled([
    getPlan({ date: dayjs().format("YYYY-MM-DD") }),
    adminApi.getTemplates()
  ]);
  if (planRes.status === "fulfilled") {
    const v = planRes.value.find(item => item.version_id === boundVersionId);
    if (v) {
      branchOptions.value = v.branches.map(b => ({
        id: b.branch_id,
        name: b.branch_name
      }));
    }
  } else {
    branchOptions.value = []; // 失败已由拦截器提示
  }
  if (templatesRes.status === "fulfilled") {
    templateOptions.value = templatesRes.value;
  } else {
    // 模板列表降级：从现有策略提取
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

watch(
  () => [
    form.branch_id,
    form.template_id,
    form.build_start_time,
    form.push_mode,
    form.push_start_time
  ],
  schedulePreview
);

// ---- 编辑 ----
function startEdit(s: StrategyItem) {
  editingId.value = s.id;
  form.branch_id = s.branch_id;
  form.template_id = s.template_id;
  form.name = s.name;
  form.build_start_time = s.build_start_time;
  form.push_start_time = s.push_start_time || "";
  form.push_mode = s.push_mode;
  form.enabled = s.enabled;
  schedulePreview();
}
function startNew() {
  editingId.value = null;
  form.branch_id = branchOptions.value[0]?.id || 0;
  form.template_id = templateOptions.value[0]?.id || 0;
  form.build_start_time = "22:00";
  form.push_start_time = "";
  form.push_mode = "normal";
  form.enabled = true;
  onBranchTemplateChange();
  schedulePreview();
}

// ---- 保存（R5-F3：在途守卫防双击重复提交，按钮同步挂 :loading）----
const saving = ref(false);
async function onSave() {
  if (saving.value) return; // 已有保存在途，忽略重复点击
  // 前置字段校验（R6-F7，对齐 StrategyEditDialog 范式）：/plan 降级空集时
  // startNew 落 branch_id=0，此前零校验直接提交非法 payload 靠后端 42201 兜底
  if (!form.branch_id) {
    ElMessage.warning("请选择策略分支");
    return;
  }
  if (!form.template_id) {
    ElMessage.warning("请选择策略模板");
    return;
  }
  if (!form.name.trim()) {
    ElMessage.warning("请输入策略名称");
    return;
  }
  if (!form.build_start_time) {
    ElMessage.warning("请选择构建开始时间");
    return;
  }
  if (preview.value?.conflict) {
    ElMessageBox.alert(
      preview.value.conflict.message || "存在时间冲突，请调整后重试",
      "策略时间冲突",
      { type: "error", confirmButtonText: "知道了" }
    );
    return;
  }
  try {
    await ElMessageBox.confirm("确认保存该策略配置？", "保存策略", {
      type: "warning",
      confirmButtonText: "确认保存",
      cancelButtonText: "取消"
    });
  } catch {
    return; // 用户取消（confirm 以 reject 形式返回，裸 await 会产生未处理 rejection）
  }
  const payload = {
    ...form,
    push_start_time: form.push_start_time || null
  };
  saving.value = true;
  try {
    if (isEditing.value) {
      await updateStrategy(editingId.value as number, { ...payload });
      ElMessage.success("策略已更新");
    } else {
      await createStrategy({ ...payload });
      ElMessage.success("策略已创建");
    }
  } catch {
    return; // 失败已由拦截器提示，保留表单便于修改重试
  } finally {
    saving.value = false;
  }
  await load();
  startNew();
}

// ---- 启停（失败后由 load 回滚 UI，不保留乐观状态）----
const togglingId = ref<number | null>(null);
async function onToggle(s: StrategyItem) {
  togglingId.value = s.id;
  try {
    // 后端为无参翻转语义：提示必须以返回的新状态为准（用旧值会文案反转）
    const updated = await toggleStrategy(s.id);
    ElMessage.success(updated.enabled ? "策略已启用" : "策略已停用");
  } catch {
    /* 失败已由拦截器提示，load() 刷新回真实状态 */
  } finally {
    togglingId.value = null;
    await load();
  }
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
    (min, x) => Math.min(min, timeToMs(x.t.start)),
    Infinity
  );
  const endMs = list.reduce(
    (max, x) => Math.max(max, timeToMs(x.t.end)),
    -Infinity
  );
  const total = Math.max(endMs - startMs, 1);
  return list.map(x => ({
    stage: x.stage,
    label: x.label,
    start: x.t.start,
    end: x.t.end,
    left: ((timeToMs(x.t.start) - startMs) / total) * 100,
    width: (Math.max(timeToMs(x.t.end) - timeToMs(x.t.start), 1) / total) * 100,
    color: STAGE_COLORS[x.stage]
  }));
});

function fmtPreview(t: string) {
  return dayjs(parseTime(t)).format("MM-DD HH:mm");
}

onMounted(async () => {
  await load();
  await loadMeta();
  // 从 URL query 读取编辑 id（深链编辑入口；原甘特页跳转源已随页面精简下线，
  // 现仅支持手工构造 /strategy?id= 的场景）
  const qid = route.query.id;
  if (qid) {
    const s = strategyList.value.find(x => x.id === Number(qid));
    if (s) startEdit(s);
  }
  // 分支与模板选项任一为空都不自动进新建态（R6-F7：此前只判模板，
  // 分支降级空集时仍落 branch_id=0 的表单）；深链编辑优先
  if (
    branchOptions.value.length > 0 &&
    templateOptions.value.length > 0 &&
    !form.branch_id
  ) {
    startNew();
  }
});
</script>

<template>
  <div class="strategy-page biz-page">
    <!-- 上半区：本版本策略列表 -->
    <div class="section biz-card">
      <div class="row-head biz-card-head">
        <span class="section-title biz-card-title"
          >本版本策略列表（{{ boundVersionName }}）</span
        >
        <el-button type="primary" size="small" @click="startNew"
          >新建策略</el-button
        >
      </div>
      <el-table v-loading="loading" :data="strategyList" style="width: 100%">
        <el-table-column prop="name" label="策略名称" min-width="180" />
        <el-table-column prop="branch_name" label="分支" width="110" />
        <el-table-column prop="template_name" label="模板" width="130" />
        <el-table-column prop="build_start_time" label="构建开始" width="110" />
        <el-table-column label="推送模式" width="130">
          <template #default="{ row }">
            {{ pushModeMeta(row.push_mode).fullLabel }}
          </template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              :loading="togglingId === row.id"
              @change="onToggle(row as StrategyItem)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              size="small"
              @click="startEdit(row as StrategyItem)"
            >
              编辑
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 下半区：策略编辑表单 + 时间线预览 -->
    <div class="section biz-card">
      <div class="form-title biz-card-title">
        {{ isEditing ? "编辑策略" : "新建策略" }}
      </div>
      <el-form :model="form" label-width="110px" class="strategy-form">
        <el-form-item label="策略分支">
          <el-select
            v-model="form.branch_id"
            style="width: 240px"
            @change="onBranchTemplateChange"
          >
            <el-option
              v-for="b in branchOptions"
              :key="b.id"
              :label="b.name"
              :value="b.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="策略模板">
          <el-select
            v-model="form.template_id"
            style="width: 240px"
            @change="onBranchTemplateChange"
          >
            <el-option
              v-for="t in templateOptions"
              :key="t.id"
              :label="t.name"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="策略名称">
          <el-input
            v-model="form.name"
            style="width: 360px"
            placeholder="策略名称"
          />
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
            <el-radio value="normal">{{
              pushModeMeta("normal").fullLabel
            }}</el-radio>
            <el-radio value="sync">{{
              pushModeMeta("sync").fullLabel
            }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="推送时间（可空）">
          <el-time-picker
            v-model="form.push_start_time"
            value-format="HH:mm"
            format="HH:mm"
            placeholder="留空=结论后推导"
            clearable
            style="width: 160px"
            @change="schedulePreview"
          />
          <span class="form-tip"
            >（设置后固定在该时间推送，可与其它策略重叠）</span
          >
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
            :style="{
              left: p.left + '%',
              width: p.width + '%',
              background: p.color
            }"
            :title="`${p.label} ${fmtPreview(p.start)} ~ ${fmtPreview(p.end)}`"
          >
            <span class="preview-phase-label">{{ p.label }}</span>
          </div>
        </div>
        <div v-else class="preview-empty">填写分支/模板/时间后自动预览</div>
        <div v-if="previewPhases.length" class="preview-legend">
          <span v-for="p in previewPhases" :key="p.stage" class="p-legend-item">
            <i class="p-dot" :style="{ background: p.color }" />
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
          :loading="saving"
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
/* 卡片容器 / 区块标题 / 卡片头样式复用全局 .biz-card / .biz-card-title / .biz-card-head */
.form-title {
  display: block;
  margin-bottom: 12px;
}
.form-tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 8px;
}
.preview-block {
  margin-top: 8px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px;
}
.preview-title {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 10px;
}
.preview-bar {
  position: relative;
  height: 40px;
  background: var(--el-fill-color);
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
  color: var(--el-text-color-secondary);
  font-size: 12px;
  padding: 12px 0;
}
.preview-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 10px;
  color: var(--el-text-color-secondary);
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
  color: var(--el-color-danger);
  font-size: 13px;
  background: var(--el-color-danger-light-9);
  border: 1px solid var(--el-color-danger-light-5);
  border-radius: 6px;
  padding: 8px 12px;
}
.form-actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}
</style>
