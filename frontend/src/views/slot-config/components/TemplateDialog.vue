<template>
  <el-dialog
    :model-value="modelValue"
    :title="editing ? `编辑时段「${editing.name}」` : '新建时段'"
    width="520px"
    destroy-on-close
    @update:model-value="value => emit('update:modelValue', value)"
    @closed="resetForm"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="92px"
      size="small"
    >
      <el-form-item label="时段名称" prop="name">
        <el-input
          v-model="form.name"
          maxlength="50"
          placeholder="如：上午构建窗口"
        />
      </el-form-item>
      <el-form-item label="开始时间" prop="start_time">
        <el-time-picker
          v-model="form.start_time"
          format="HH:mm"
          value-format="HH:mm"
          placeholder="选择开始时间"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="结束时间" prop="end_time">
        <el-time-picker
          v-model="form.end_time"
          format="HH:mm"
          value-format="HH:mm"
          placeholder="需晚于开始时间（不支持跨天）"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="适用星期" prop="weekdays">
        <el-select
          v-model="form.weekdays"
          multiple
          collapse-tags
          placeholder="留空表示每天适用"
          style="width: 100%"
        >
          <el-option
            v-for="w in WEEKDAYS"
            :key="w.value"
            :label="w.label"
            :value="w.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="生效范围" prop="effectiveRange">
        <el-date-picker
          v-model="form.effectiveRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="~"
          start-placeholder="起始日（可空）"
          end-placeholder="截止日（可空）"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="标识色" prop="color">
        <div class="color-picker-row">
          <span
            v-for="c in COLOR_PRESETS"
            :key="c"
            class="color-swatch"
            :class="{ active: form.color === c }"
            :style="{ background: c }"
            role="button"
            :aria-label="`选择颜色 ${c}`"
            @click="form.color = c"
          />
        </div>
      </el-form-item>
      <el-form-item label="排序" prop="sort_order">
        <el-input-number
          v-model="form.sort_order"
          :min="0"
          :max="999"
          size="small"
        />
        <span class="field-tip">数值小的在日历中靠前展示</span>
      </el-form-item>
      <el-form-item label="启用" prop="enabled">
        <el-switch v-model="form.enabled" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave"
        >保存</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import type { FormInstance, FormRules } from "element-plus";
import { ElMessage } from "element-plus";
import {
  createSlotTemplate,
  updateSlotTemplate,
  type SlotTemplateItem
} from "@/api/slotBooking";

defineOptions({ name: "SlotTemplateDialog" });

const props = defineProps<{
  modelValue: boolean;
  editing: SlotTemplateItem | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "saved", payload: { warnings: string[] }): void;
}>();

const COLOR_PRESETS = [
  "#409eff",
  "#67c23a",
  "#e6a23c",
  "#f56c6c",
  "#909399",
  "#00c4cc",
  "#8b5cf6",
  "#ff7d00"
];

const WEEKDAYS = [
  { value: "1", label: "周一" },
  { value: "2", label: "周二" },
  { value: "3", label: "周三" },
  { value: "4", label: "周四" },
  { value: "5", label: "周五" },
  { value: "6", label: "周六" },
  { value: "7", label: "周日" }
];

const formRef = ref<FormInstance>();
const saving = ref(false);

const form = reactive({
  name: "",
  start_time: "",
  end_time: "",
  weekdays: [] as string[],
  effectiveRange: null as [string, string] | null,
  color: "#409eff",
  sort_order: 0,
  enabled: true
});

const rules: FormRules = {
  name: [{ required: true, message: "请输入时段名称", trigger: "blur" }],
  start_time: [
    { required: true, message: "请选择开始时间", trigger: "change" }
  ],
  end_time: [
    { required: true, message: "请选择结束时间", trigger: "change" },
    {
      validator: (_rule, value: string, callback) => {
        if (value && form.start_time && value <= form.start_time) {
          callback(new Error("不支持跨天时段，结束时间需晚于开始时间"));
        } else {
          callback();
        }
      },
      trigger: "change"
    }
  ]
};

function resetForm() {
  if (props.editing) {
    form.name = props.editing.name;
    form.start_time = props.editing.start_time;
    form.end_time = props.editing.end_time;
    form.weekdays = props.editing.weekdays
      ? props.editing.weekdays.split(",")
      : [];
    form.effectiveRange =
      props.editing.effective_from || props.editing.effective_to
        ? [props.editing.effective_from ?? "", props.editing.effective_to ?? ""]
        : null;
    form.color = props.editing.color;
    form.sort_order = props.editing.sort_order;
    form.enabled = props.editing.enabled;
  } else {
    form.name = "";
    form.start_time = "";
    form.end_time = "";
    form.weekdays = [];
    form.effectiveRange = null;
    form.color = "#409eff";
    form.sort_order = 0;
    form.enabled = true;
  }
}

watch(
  () => props.modelValue,
  visible => {
    if (visible) resetForm();
  }
);

function buildPayload() {
  return {
    name: form.name.trim(),
    start_time: form.start_time,
    end_time: form.end_time,
    weekdays: form.weekdays.join(","),
    effective_from: form.effectiveRange?.[0] || null,
    effective_to: form.effectiveRange?.[1] || null,
    color: form.color,
    sort_order: form.sort_order,
    enabled: form.enabled
  };
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  saving.value = true;
  try {
    const result = props.editing
      ? await updateSlotTemplate(props.editing.id, buildPayload())
      : await createSlotTemplate(buildPayload());
    emit("saved", { warnings: result.warnings ?? [] });
  } catch {
    // 重名/校验错误：拦截器已提示
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped lang="scss">
.color-picker-row {
  display: flex;
  gap: 8px;

  .color-swatch {
    width: 22px;
    height: 22px;
    border-radius: 6px;
    cursor: pointer;
    border: 2px solid transparent;
    transition: transform 0.15s var(--el-transition-fade);

    &:hover {
      transform: scale(1.1);
    }

    &.active {
      border-color: var(--el-text-color-primary);
      box-shadow: 0 0 0 2px var(--el-color-primary-light-7);
    }
  }
}

.field-tip {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
