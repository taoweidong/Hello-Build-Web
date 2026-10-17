<template>
  <el-dialog
    :model-value="modelValue"
    title="策略详情与借用申请"
    width="560px"
    @update:model-value="value => emit('update:modelValue', value)"
    @open="onOpen"
    @closed="reset"
  >
    <!-- 策略只读信息 -->
    <el-descriptions :column="2" border size="small" class="info-desc">
      <el-descriptions-item label="策略名称" :span="2">
        {{ strategy?.strategy_name }}
      </el-descriptions-item>
      <el-descriptions-item label="来源版本">
        {{ strategy?.version_name }}
      </el-descriptions-item>
      <el-descriptions-item label="分支">
        {{ strategy?.branch_name }}
      </el-descriptions-item>
      <el-descriptions-item label="冒烟模板">
        {{ strategy?.template_name }}
      </el-descriptions-item>
      <el-descriptions-item label="构建时间">
        {{ strategy?.build_start_time }}
      </el-descriptions-item>
      <el-descriptions-item label="推送模式">
        {{ pushModeMeta(strategy?.push_mode).label }}
      </el-descriptions-item>
      <el-descriptions-item label="推送时间">
        {{ strategy?.push_start_time || "结论后推导" }}
      </el-descriptions-item>
    </el-descriptions>

    <div class="borrow-tip">
      您没有该版本的策略修改权限。如需借用此构建时间到您的版本，请填写以下申请，
      提交后将生成借用电子流，由来源版本负责人审批。
    </div>

    <!-- 借用申请表单 -->
    <el-form :model="form" label-width="96px">
      <el-form-item label="目标版本">
        <el-select
          v-model="form.target_version_id"
          placeholder="选择要借用到的版本"
          style="width: 100%"
          @change="form.target_branch_id = undefined"
        >
          <el-option
            v-for="v in targetVersionOptions"
            :key="v.version_id"
            :label="v.version_name"
            :value="v.version_id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="目标分支">
        <el-select
          v-model="form.target_branch_id"
          placeholder="选择目标分支"
          style="width: 100%"
          :disabled="!form.target_version_id"
        >
          <el-option
            v-for="b in targetBranchOptions"
            :key="b.branch_id"
            :label="b.branch_name"
            :value="b.branch_id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="新构建时间">
        <el-time-picker
          v-model="form.new_build_time"
          value-format="HH:mm"
          format="HH:mm"
          placeholder="借用后的构建时间"
          style="width: 160px"
        />
      </el-form-item>
      <el-form-item label="借用原因">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="2"
          maxlength="200"
          show-word-limit
          placeholder="说明借用用途，便于审批人判断"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="onSubmit">
        提交借用申请
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// 版本策略全景页 - 无修改权限用户的策略详情 + 借用申请弹窗
// 借用 = 发起电子流（借用至自己的版本/分支 + 新时间），由来源版本负责人在「借用审批」页审批
import { computed, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import dayjs from "dayjs";
import { getPlan, type PlanVersion } from "@/api/plan";
import { createBorrowFlow } from "@/api/borrowFlow";
import type { WeeklyStrategy } from "@/api/types";
import { getCurrentUser } from "@/utils/business";
// 推送模式文案唯一来源（views/constants，页面内禁止复制措辞）
import { pushModeMeta } from "@/views/constants";

defineOptions({ name: "WeeklyNewStrategyBorrowDialog" });

const props = defineProps<{
  modelValue: boolean;
  /** 被借用策略（来自周视图数据，只读字段足够展示；version_name 由父级合并注入） */
  strategy: (WeeklyStrategy & { version_name?: string }) | null;
  /** 当前查看的版本 id（目标版本不能与它相同，服务端亦校验） */
  currentVersionId: number | undefined;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  /** 借用申请提交成功即通知父级（R5-F14）：全景 ScheduleDialogs 据此 data.refresh()，
   *  否则新借用事件最长延迟一个轮询周期才上画布；weekly-new 侧不监听，零破坏 */
  (e: "created"): void;
}>();

const router = useRouter();
const currentUser = getCurrentUser();

const form = reactive({
  target_version_id: undefined as number | undefined,
  target_branch_id: undefined as number | undefined,
  new_build_time: "22:00",
  reason: ""
});
const submitting = ref(false);

// 版本/分支选项：来自甘特聚合接口（全版本分支结构，只读）
const planVersions = ref<PlanVersion[]>([]);

const targetVersionOptions = computed(() =>
  planVersions.value.filter(v => v.version_id !== props.currentVersionId)
);

const targetBranchOptions = computed(
  () =>
    planVersions.value.find(v => v.version_id === form.target_version_id)
      ?.branches ?? []
);

async function onOpen() {
  const s = props.strategy;
  if (!s) return;
  // 默认时间沿用被借用策略的构建时间；PM 默认选自己绑定的版本
  form.new_build_time = s.build_start_time;
  form.target_branch_id = undefined;
  form.reason = "";
  form.target_version_id =
    currentUser?.bound_version_id &&
    currentUser.bound_version_id !== props.currentVersionId
      ? currentUser.bound_version_id
      : undefined;
  if (planVersions.value.length === 0) {
    try {
      planVersions.value = await getPlan({
        date: dayjs().format("YYYY-MM-DD")
      });
    } catch {
      planVersions.value = []; // 拦截器已提示
    }
  }
}

function reset() {
  form.target_version_id = undefined;
  form.target_branch_id = undefined;
  form.reason = "";
}

async function onSubmit() {
  if (!props.strategy) return;
  if (!form.target_version_id || !form.target_branch_id) {
    ElMessage.warning("请选择目标版本与分支");
    return;
  }
  submitting.value = true;
  try {
    await createBorrowFlow({
      strategy_id: props.strategy.strategy_id,
      target_branch_id: form.target_branch_id,
      new_build_time: form.new_build_time,
      reason: form.reason
    });
    emit("created");
    emit("update:modelValue", false);
    ElMessageBox.confirm(
      "借用电子流已提交，等待来源版本负责人审批。可在「借用审批」页查看进度。",
      "提交成功",
      {
        confirmButtonText: "前往审批页",
        cancelButtonText: "留在本页",
        type: "success"
      }
    )
      .then(() => router.push("/borrow-flow"))
      .catch(() => undefined);
  } catch {
    // 失败已由拦截器提示（如同策略重复 pending 40903），保留弹窗便于修改重试
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped lang="scss">
.info-desc {
  margin-bottom: 12px;
}

.borrow-tip {
  margin-bottom: 12px;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 18px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
}
</style>
