<template>
  <el-dialog
    :model-value="modelValue"
    :title="`${weekLabel} 抢占时间段`"
    width="480px"
    destroy-on-close
    @update:model-value="value => emit('update:modelValue', value)"
    @closed="resetForm"
  >
    <div v-if="template" class="slot-brief">
      <el-icon :size="16"><Calendar /></el-icon>
      <span class="brief-main">
        {{ dateLabel }}（{{ weekLabel }}）{{ template.start_time }} –
        {{ template.end_time }}
      </span>
      <el-tag size="small" type="info" effect="plain">{{
        durationText
      }}</el-tag>
    </div>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="88px"
      size="small"
      @submit.prevent
    >
      <el-form-item label="关联版本" prop="version_id">
        <el-select
          v-model="form.version_id"
          filterable
          placeholder="选择版本"
          style="width: 100%"
          @change="onVersionChange"
        >
          <el-option
            v-for="v in versionOptions"
            :key="v.version_id"
            :label="v.version_name"
            :value="v.version_id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="关联分支" prop="branch_id">
        <el-select
          v-model="form.branch_id"
          filterable
          :disabled="!form.version_id"
          :placeholder="form.version_id ? '选择分支' : '请先选择版本'"
          style="width: 100%"
        >
          <el-option
            v-for="b in branchOptions"
            :key="b.branch_id"
            :label="b.branch_name"
            :value="b.branch_id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="用途说明" prop="purpose">
        <el-input
          v-model="form.purpose"
          type="textarea"
          :rows="3"
          maxlength="200"
          show-word-limit
          placeholder="2~200 字，如：27A master 回归验证"
        />
      </el-form-item>
    </el-form>

    <el-alert
      title="抢占后不可修改；如需调整请先释放该时段"
      type="warning"
      :closable="false"
      show-icon
      class="submit-tip"
    />

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit"
        >确认抢占</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import dayjs from "dayjs";
import type { FormInstance, FormRules } from "element-plus";
import { ElMessage } from "element-plus";
import Calendar from "~icons/ep/calendar";
import { getPlan } from "@/api/plan";
import type { PlanVersion } from "@/api/plan";
import { createBooking, type SlotTemplateItem } from "@/api/slotBooking";

defineOptions({ name: "SlotBookingDialog" });

const props = defineProps<{
  modelValue: boolean;
  date: string;
  template: SlotTemplateItem | null;
  horizonEnd: string;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "booked"): void;
}>();

const formRef = ref<FormInstance>();
const submitting = ref(false);
const planData = ref<PlanVersion[]>([]);

const form = reactive({
  version_id: null as number | null,
  branch_id: null as number | null,
  purpose: ""
});

const rules: FormRules = {
  version_id: [
    { required: true, message: "请选择关联版本", trigger: "change" }
  ],
  branch_id: [{ required: true, message: "请选择关联分支", trigger: "change" }],
  purpose: [
    { required: true, message: "请填写用途说明", trigger: "blur" },
    { min: 2, max: 200, message: "用途说明需 2~200 字", trigger: "blur" }
  ]
};

const versionOptions = computed(() => planData.value);
const branchOptions = computed(
  () =>
    planData.value.find(v => v.version_id === form.version_id)?.branches ?? []
);

const dateLabel = computed(() => dayjs(props.date).format("M月D日"));
const weekLabel = computed(() => {
  const names = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  return names[dayjs(props.date).day()];
});
const durationText = computed(() => {
  if (!props.template) return "";
  const [sh, sm] = props.template.start_time.split(":").map(Number);
  const [eh, em] = props.template.end_time.split(":").map(Number);
  const minutes = eh * 60 + em - (sh * 60 + sm);
  if (minutes <= 0) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return (
    [h ? `${h}小时` : "", m ? `${m}分` : ""].filter(Boolean).join("") ||
    `${minutes}分`
  );
});

function onVersionChange() {
  form.branch_id = null; // 切换版本清空已选分支
}

function resetForm() {
  form.version_id = null;
  form.branch_id = null;
  form.purpose = "";
  planData.value = [];
}

watch(
  () => props.modelValue,
  async visible => {
    if (visible) {
      try {
        planData.value = await getPlan({ date: props.date });
      } catch {
        planData.value = []; // 拦截器已提示
      }
    }
  }
);

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid || !props.template) return;
  if (props.date > props.horizonEnd) {
    ElMessage.warning("超出可抢占窗口，请选择更近的日期");
    return;
  }
  submitting.value = true;
  try {
    await createBooking({
      date: props.date,
      template_id: props.template.id,
      purpose: form.purpose.trim(),
      version_id: form.version_id as number,
      branch_id: form.branch_id as number
    });
    emit("booked");
  } catch {
    // 40904 抢占冲突等：拦截器已 ElMessage 提示，弹窗保持打开便于重选
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped lang="scss">
.slot-brief {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 14px;
  border-radius: 6px;
  background: var(--el-color-primary-light-9);
  color: var(--el-text-color-primary);
  font-size: 14px;

  .brief-main {
    flex: 1;
    font-weight: 600;
  }
}

.submit-tip {
  margin-top: 4px;
}
</style>
