<script setup lang="ts">
// 系统管理 - 策略配置 Tab（管理员全量 CRUD）：筛选 + 列表 + 编辑弹窗（预览复用 composable）
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { adminApi } from "@/api/admin";
import type { StrategyItem, TemplateItem, VersionItem } from "@/api/types";
import type { StrategyForm } from "@/api/strategy";
// 推送模式文案唯一来源（views/constants，页面内禁止复制措辞）
import { pushModeMeta } from "@/views/constants";
import { useStrategyPreview } from "@/composables/useStrategyPreview";

defineOptions({ name: "AdminStrategiesTab" });

const props = defineProps<{
  versions: VersionItem[];
  templates: TemplateItem[];
}>();

const adminStrategies = ref<StrategyItem[]>([]);
const adminVersionId = ref<number | undefined>(undefined);
const adminBranchId = ref<number | undefined>(undefined);
const adminStrategyDialog = ref(false);
const adminStrategyForm = reactive<StrategyForm>({
  branch_id: 0,
  template_id: 0,
  name: "",
  build_start_time: "22:00",
  push_start_time: "" as string,
  push_mode: "normal",
  enabled: true
});
const adminEditingId = ref<number | null>(null);
const adminDialogVersionId = ref<number | undefined>(undefined);
const loading = ref(false);
/** 弹窗保存请求进行中（按钮 :loading 防双击重复提交） */
const savingStrategy = ref(false);

// 弹窗策略预览（防抖 + 过期守卫，与 PM 策略页共用实现）
// 编辑态透传 id，预览接口据此排除被编辑策略自身，避免原时间未变时误报自冲突
const {
  preview: adminPreview,
  schedule: scheduleAdminPreview,
  reset: resetAdminPreview
} = useStrategyPreview(() =>
  adminStrategyForm.branch_id && adminStrategyForm.template_id
    ? { ...adminStrategyForm, id: adminEditingId.value ?? undefined }
    : null
);

/** 弹窗分支选项：基于弹窗内所选版本 */
const adminBranchOptions = computed(() => {
  if (!adminDialogVersionId.value) return [];
  const v = props.versions.find(x => x.id === adminDialogVersionId.value);
  return (v?.branches || []).map(b => ({ id: b.id, name: b.name }));
});

/** 工具栏分支选项：基于工具栏版本筛选 */
const adminFilterBranchOptions = computed(() => {
  if (!adminVersionId.value) return [];
  const v = props.versions.find(x => x.id === adminVersionId.value);
  return (v?.branches || []).map(b => ({ id: b.id, name: b.name }));
});

async function loadAdminStrategies() {
  loading.value = true;
  try {
    adminStrategies.value = await adminApi.getAdminStrategies({
      version_id: adminVersionId.value,
      branch_id: adminBranchId.value
    });
  } catch {
    ElMessage.error("策略列表加载失败");
  } finally {
    loading.value = false;
  }
}

function onAdminVersionChange() {
  adminBranchId.value = undefined;
  loadAdminStrategies();
}

function openAdminStrategy(s?: StrategyItem) {
  adminStrategyDialog.value = true;
  resetAdminPreview();
  if (s) {
    adminDialogVersionId.value = s.version_id;
    adminEditingId.value = s.id;
    adminStrategyForm.branch_id = s.branch_id;
    adminStrategyForm.template_id = s.template_id;
    adminStrategyForm.name = s.name;
    adminStrategyForm.build_start_time = s.build_start_time;
    adminStrategyForm.push_start_time = s.push_start_time || "";
    adminStrategyForm.push_mode = s.push_mode;
    adminStrategyForm.enabled = s.enabled;
  } else {
    adminDialogVersionId.value = adminVersionId.value || undefined;
    adminEditingId.value = null;
    adminStrategyForm.branch_id = 0;
    adminStrategyForm.template_id = 0;
    adminStrategyForm.name = "";
    adminStrategyForm.build_start_time = "22:00";
    adminStrategyForm.push_start_time = "";
    adminStrategyForm.push_mode = "normal";
    adminStrategyForm.enabled = true;
  }
  scheduleAdminPreview();
}

async function saveAdminStrategy() {
  if (!adminStrategyForm.branch_id) {
    ElMessage.warning("请选择策略分支");
    return;
  }
  if (!adminStrategyForm.template_id) {
    ElMessage.warning("请选择策略模板");
    return;
  }
  if (!adminStrategyForm.name) {
    ElMessage.warning("请输入策略名称");
    return;
  }
  if (adminPreview.value?.conflict) {
    ElMessageBox.alert(
      adminPreview.value.conflict.message || "存在时间冲突",
      "策略时间冲突",
      {
        type: "error",
        confirmButtonText: "知道了"
      }
    );
    return;
  }
  const payload = {
    branch_id: adminStrategyForm.branch_id,
    template_id: adminStrategyForm.template_id,
    name: adminStrategyForm.name,
    build_start_time: adminStrategyForm.build_start_time,
    push_start_time: adminStrategyForm.push_start_time || null,
    push_mode: adminStrategyForm.push_mode,
    enabled: adminStrategyForm.enabled
  };
  // 动作路径必须 try/catch/finally 完整：失败由拦截器提示，禁止裸 await 逃逸（R3-F5）
  savingStrategy.value = true;
  try {
    if (adminEditingId.value) {
      await adminApi.updateAdminStrategy(adminEditingId.value, payload);
      ElMessage.success("策略已更新");
    } else {
      await adminApi.createAdminStrategy(payload);
      ElMessage.success("策略已创建");
    }
    adminStrategyDialog.value = false;
    loadAdminStrategies();
  } catch {
    // 失败已由拦截器提示（含 40901 冲突专用弹框），保留弹窗便于修改重试
  } finally {
    savingStrategy.value = false;
  }
}

// 注意：adminApi.toggleAdminStrategy 是无参翻转语义（后端翻转 enabled），切不可传 enabled 参数
// 开关用 :model-value 受控 + finally 重载列表，失败不残留乐观状态
const togglingStrategyId = ref<number | null>(null);
async function toggleAdminStrategy(s: StrategyItem) {
  togglingStrategyId.value = s.id;
  try {
    // 提示以返回的新状态为准（用翻转前旧值会文案反转）
    const updated = await adminApi.toggleAdminStrategy(s.id);
    ElMessage.success(updated.enabled ? "策略已启用" : "策略已停用");
  } catch {
    /* 失败已由拦截器提示，重载列表刷新回真实状态 */
  } finally {
    togglingStrategyId.value = null;
    loadAdminStrategies();
  }
}

async function deleteAdminStrategy(s: StrategyItem) {
  try {
    await ElMessageBox.confirm(
      `确认删除策略「${s.name}」？将级联清理其关联执行数据。`,
      "删除策略",
      {
        type: "warning",
        confirmButtonText: "确认删除",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return; // 用户取消
  }
  try {
    await adminApi.deleteAdminStrategy(s.id);
  } catch {
    return; // 失败已由拦截器提示
  }
  ElMessage.success("策略已删除");
  loadAdminStrategies();
}

onMounted(loadAdminStrategies);
</script>

<template>
  <div>
    <div class="toolbar">
      <el-select
        v-model="adminVersionId"
        placeholder="全部版本"
        clearable
        style="width: 160px"
        @change="onAdminVersionChange"
      >
        <el-option
          v-for="v in versions"
          :key="v.id"
          :label="v.name"
          :value="v.id"
        />
      </el-select>
      <el-select
        v-model="adminBranchId"
        placeholder="全部分支"
        clearable
        style="width: 160px"
        :disabled="!adminVersionId"
        @change="loadAdminStrategies"
      >
        <el-option
          v-for="b in adminFilterBranchOptions"
          :key="b.id"
          :label="b.name"
          :value="b.id"
        />
      </el-select>
      <el-button type="primary" size="small" @click="loadAdminStrategies"
        >查询</el-button
      >
      <el-button type="primary" size="small" @click="openAdminStrategy()"
        >新建策略</el-button
      >
    </div>
    <el-table v-loading="loading" :data="adminStrategies" style="width: 100%">
      <el-table-column prop="name" label="策略名称" min-width="180" />
      <el-table-column prop="version_name" label="版本" width="90" />
      <el-table-column prop="branch_name" label="分支" width="100" />
      <el-table-column prop="template_name" label="模板" width="120" />
      <el-table-column prop="build_start_time" label="构建开始" width="100" />
      <el-table-column label="推送" width="110">
        <template #default="{ row }">
          {{ row.push_start_time || "结论后推导" }}
        </template>
      </el-table-column>
      <el-table-column label="启用" width="80">
        <template #default="{ row }">
          <el-switch
            :model-value="row.enabled"
            :loading="togglingStrategyId === row.id"
            @change="toggleAdminStrategy(row as StrategyItem)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            size="small"
            @click="openAdminStrategy(row as StrategyItem)"
            >编辑</el-button
          >
          <el-button
            type="danger"
            link
            size="small"
            @click="deleteAdminStrategy(row as StrategyItem)"
            >删除</el-button
          >
        </template>
      </el-table-column>
    </el-table>

    <!-- 策略编辑弹窗（管理员） -->
    <el-dialog
      v-model="adminStrategyDialog"
      :title="adminEditingId ? '编辑策略' : '新建策略'"
      width="480px"
      @closed="resetAdminPreview"
    >
      <el-form :model="adminStrategyForm" label-width="110px">
        <el-form-item label="策略版本">
          <el-select
            v-model="adminDialogVersionId"
            style="width: 100%"
            @change="
              adminStrategyForm.branch_id = 0;
              scheduleAdminPreview();
            "
          >
            <el-option
              v-for="v in versions"
              :key="v.id"
              :label="v.name"
              :value="v.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="策略分支">
          <el-select
            v-model="adminStrategyForm.branch_id"
            style="width: 100%"
            @change="scheduleAdminPreview"
          >
            <el-option
              v-for="b in adminBranchOptions"
              :key="b.id"
              :label="b.name"
              :value="b.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="策略模板">
          <el-select
            v-model="adminStrategyForm.template_id"
            style="width: 100%"
            @change="scheduleAdminPreview"
          >
            <el-option
              v-for="t in templates"
              :key="t.id"
              :label="t.name"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="策略名称">
          <el-input v-model="adminStrategyForm.name" placeholder="策略名称" />
        </el-form-item>
        <el-form-item label="构建开始时间">
          <el-time-picker
            v-model="adminStrategyForm.build_start_time"
            value-format="HH:mm"
            format="HH:mm"
            style="width: 160px"
            @change="scheduleAdminPreview"
          />
        </el-form-item>
        <el-form-item label="推送时间（可空）">
          <el-time-picker
            v-model="adminStrategyForm.push_start_time"
            value-format="HH:mm"
            format="HH:mm"
            placeholder="留空=结论后推导"
            clearable
            style="width: 160px"
            @change="scheduleAdminPreview"
          />
        </el-form-item>
        <el-form-item label="推送模式">
          <el-radio-group
            v-model="adminStrategyForm.push_mode"
            @change="scheduleAdminPreview"
          >
            <el-radio value="normal">{{
              pushModeMeta("normal").fullLabel
            }}</el-radio>
            <el-radio value="sync">{{
              pushModeMeta("sync").fullLabel
            }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="adminStrategyForm.enabled" />
        </el-form-item>
        <el-form-item v-if="adminPreview?.conflict" label="冲突">
          <span class="preview-conflict">
            {{ adminPreview.conflict.message || "存在时间冲突" }}
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adminStrategyDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="savingStrategy"
          :disabled="!!adminPreview?.conflict"
          @click="saveAdminStrategy"
          >保存</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  margin-bottom: 12px;
}
.preview-conflict {
  color: var(--el-color-danger);
  font-size: 13px;
}
</style>
