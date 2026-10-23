<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑策略（调度全景）"
    width="520px"
    @update:model-value="value => emit('update:modelValue', value)"
    @closed="reset"
  >
    <el-form :model="form" label-width="96px">
      <el-form-item label="策略分支">
        <el-select
          v-model="form.branch_id"
          style="width: 100%"
          @change="schedule"
        >
          <el-option
            v-for="b in branches"
            :key="b.branch_id"
            :label="b.branch_name"
            :value="b.branch_id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="策略模板">
        <el-select
          v-model="form.template_id"
          style="width: 100%"
          @change="schedule"
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
        <el-input v-model="form.name" placeholder="策略名称" />
      </el-form-item>
      <el-form-item label="构建时间">
        <el-time-picker
          v-model="form.build_start_time"
          value-format="HH:mm"
          format="HH:mm"
          placeholder="每天循环，支持跨天"
          style="width: 160px"
          @change="schedule"
        />
        <el-tooltip
          content="每日循环执行；冒烟耗时较长时支持跨天"
          placement="top"
        >
          <el-icon class="field-hint">
            <IconifyIconOffline :icon="QuestionFilled" />
          </el-icon>
        </el-tooltip>
      </el-form-item>
      <el-form-item label="推送模式">
        <el-radio-group v-model="form.push_mode" @change="schedule">
          <el-radio value="normal">{{
            pushModeMeta("normal").fullLabel
          }}</el-radio>
          <el-radio value="sync">{{ pushModeMeta("sync").fullLabel }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="推送时间">
        <el-time-picker
          v-model="form.push_start_time"
          value-format="HH:mm"
          format="HH:mm"
          placeholder="留空=结论后推导"
          clearable
          style="width: 160px"
          @change="schedule"
        />
        <el-tooltip
          content="设置后固定在该时间推送，可与其它策略时段重叠"
          placement="top"
        >
          <el-icon class="field-hint">
            <IconifyIconOffline :icon="QuestionFilled" />
          </el-icon>
        </el-tooltip>
      </el-form-item>
      <el-form-item label="启用">
        <el-switch v-model="form.enabled" @change="schedule" />
      </el-form-item>
      <el-form-item v-if="preview?.conflict" label="冲突">
        <span class="preview-conflict">
          {{ preview.conflict.message || "存在时间冲突" }}
        </span>
      </el-form-item>
    </el-form>

    <!-- 时间线实时预览（两列网格，单格不折行；完整可视化见策略配置页） -->
    <div v-if="phaseLines.length" class="preview-lines">
      <span v-for="l in phaseLines" :key="l.label" class="preview-line">
        <b>{{ l.label }}</b> {{ l.text }}
      </span>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!!preview?.conflict"
        @click="onSave"
      >
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// 版本策略全景页 - 策略编辑弹窗（仅内部维护人员可见入口）
// 复用 PM/admin 共用写路径（PATCH /strategies/:id，服务端统一校验）与预览 composable
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import QuestionFilled from "~icons/ep/question-filled";
import { adminApi } from "@/api/admin";
import { updateStrategy, type StrategyForm } from "@/api/strategy";
import type { StrategyItem, TemplateItem } from "@/api/types";
import { formatTime } from "@/utils/business";
// 推送模式文案唯一来源（views/constants，页面内禁止复制措辞）
import { pushModeMeta } from "@/views/constants";
import { useStrategyPreview } from "@/composables/useStrategyPreview";

defineOptions({ name: "WeeklyNewStrategyEditDialog" });

const props = defineProps<{
  modelValue: boolean;
  /** 被编辑策略（打开时必须非空） */
  strategy: StrategyItem | null;
  /** 当前版本的分支选项（来自周视图数据） */
  branches: { branch_id: number; branch_name: string }[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved"): void;
}>();

const form = reactive<StrategyForm & { id?: number }>({
  id: undefined,
  branch_id: 0,
  template_id: 0,
  name: "",
  build_start_time: "22:00",
  push_start_time: "" as string,
  push_mode: "normal",
  enabled: true
});
const saving = ref(false);

// 模板选项：优先 /admin/templates（admin/pm 均可读），失败降级为当前策略自身的模板
const templateOptions = ref<TemplateItem[]>([]);
// 是否已成功拉取模板（R4-F13/F-L9）：区分「成功加载」与「降级」——此前以
// 「数组非空」判定已加载，降级填充的单选项会把后续每次打开锁死且无提示；
// 现降级不置位，下次打开自动重试拉取
const templatesLoaded = ref(false);
watch(
  () => props.modelValue,
  async visible => {
    if (!visible || !props.strategy) return;
    fillForm();
    if (!templatesLoaded.value) {
      try {
        // 统一走 API 层（禁止裸 http.get 绕过模块封装，R3-F6）
        templateOptions.value = await adminApi.getTemplates();
        templatesLoaded.value = true;
      } catch {
        templateOptions.value = [
          {
            id: props.strategy.template_id,
            name: props.strategy.template_name,
            smoke_minutes: 0,
            analysis_minutes: 0
          }
        ];
      }
    }
    schedule();
  },
  // immediate（R6-F16）：ScheduleDialogs 以 v-if 挂载本弹窗（挂载即 modelValue=true），
  // 无 immediate 时 watch 永不触发 → 表单不回填、模板列表不加载（保存会以默认值覆盖）
  { immediate: true }
);

function fillForm() {
  const s = props.strategy;
  if (!s) return;
  form.id = s.id;
  form.branch_id = s.branch_id;
  form.template_id = s.template_id;
  form.name = s.name;
  form.build_start_time = s.build_start_time;
  form.push_start_time = s.push_start_time || "";
  form.push_mode = s.push_mode;
  form.enabled = s.enabled;
}

// 预览：编辑态透传 id 排除自身，避免原时间未变时误报自冲突
const { preview, schedule, reset } = useStrategyPreview(() =>
  form.branch_id && form.template_id ? form : null
);

/** 紧凑时间线文本（构建/冒烟/分析/推送 各阶段起止） */
const phaseLines = computed(() => {
  const tl = preview.value?.timeline;
  if (!tl) return [];
  return [
    { label: "推送", t: tl.push },
    { label: "构建", t: tl.build },
    { label: "冒烟", t: tl.smoke },
    { label: "分析", t: tl.analysis }
  ]
    .filter(x => x.t)
    .map(x => ({
      label: x.label,
      text: `${formatTime(x.t!.start)} ~ ${formatTime(x.t!.end)}`
    }));
});

async function onSave() {
  if (!form.branch_id) {
    ElMessage.warning("请选择策略分支");
    return;
  }
  if (!form.template_id) {
    ElMessage.warning("请选择策略模板");
    return;
  }
  if (!form.name) {
    ElMessage.warning("请输入策略名称");
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
  if (!props.strategy) return;
  saving.value = true;
  try {
    const payload: StrategyForm = {
      branch_id: form.branch_id,
      template_id: form.template_id,
      name: form.name,
      build_start_time: form.build_start_time,
      push_mode: form.push_mode,
      push_start_time: form.push_start_time || null,
      enabled: form.enabled
    };
    await updateStrategy(props.strategy.id, payload);
    ElMessage.success("策略已更新");
    emit("update:modelValue", false);
    emit("saved");
  } catch {
    // 失败已由拦截器提示（含 40901 冲突专用弹框），保留弹窗便于修改重试
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped lang="scss">
/* 表单行不换行：标签单行、控件行禁止折行 */
:deep(.el-form-item__label) {
  white-space: nowrap;
}

:deep(.el-form-item__content) {
  flex-wrap: nowrap;
}

.field-hint {
  margin-left: 6px;
  font-size: 14px;
  color: var(--el-text-color-placeholder);
  cursor: help;
  flex: none;
}

.preview-conflict {
  color: var(--el-color-danger);
  font-size: 13px;
}

/* 时间线预览：两列网格，单格内不折行（超长省略） */
.preview-lines {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 12px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border-radius: 4px;

  .preview-line {
    display: flex;
    align-items: center;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;

    b {
      flex: none;
      font-weight: 600;
      margin-right: 4px;
    }
  }
}
</style>
