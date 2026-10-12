<template>
  <div v-if="bp">
    <el-form label-width="120px" size="small" :disabled="myRole !== 'ADMIN'">
      <el-form-item label="启动命令">
        <el-input
          v-model="form.command"
          placeholder="如 python manage.py runserver"
        />
      </el-form-item>
      <el-form-item label="参数">
        <div v-for="(arg, idx) in form.args" :key="idx" class="kv-row">
          <el-input v-model="form.args[idx]" placeholder="参数值" />
          <el-button text type="danger" @click="form.args.splice(idx, 1)"
            >删除</el-button
          >
        </div>
        <el-button size="small" text type="primary" @click="form.args.push('')"
          >＋ 添加参数</el-button
        >
      </el-form-item>
      <el-form-item label="环境变量">
        <div v-for="(key, idx) in envKeys" :key="idx" class="kv-row">
          <!-- key 可编辑：:model-value + 事件重命名（computed 不可写，禁止 v-model 直绑） -->
          <el-input
            :model-value="key"
            placeholder="KEY"
            style="width: 40%"
            @update:model-value="v => renameEnv(idx, v)"
          />
          <!-- value 同步回 form.env_vars -->
          <el-input
            :model-value="form.env_vars[key] ?? ''"
            placeholder="VALUE"
            style="width: 40%"
            @update:model-value="v => bindEnv(idx, v)"
          />
          <el-button text type="danger" @click="removeEnv(idx)">删除</el-button>
        </div>
        <el-button size="small" text type="primary" @click="addEnv"
          >＋ 添加变量</el-button
        >
      </el-form-item>
      <el-form-item label="工作目录">
        <el-input
          v-model="form.working_directory"
          placeholder="绝对路径，可空"
        />
      </el-form-item>
      <el-form-item label="启动超时(秒)">
        <el-input-number v-model="form.timeout_seconds" :min="1" :max="3600" />
      </el-form-item>
      <el-form-item label="自动重启">
        <el-switch v-model="form.auto_restart" />
      </el-form-item>
      <el-form-item v-if="form.raw_json" label="原始配置">
        <pre class="raw-json">{{ form.raw_json }}</pre>
      </el-form-item>
      <el-form-item v-if="myRole === 'ADMIN'">
        <el-button type="primary" :loading="saving" @click="onSaveClick"
          >保存参数</el-button
        >
      </el-form-item>
    </el-form>
  </div>
  <el-empty v-else description="请先选择要编辑的工程" />
</template>

<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import type {
  BranchRole,
  BranchProjectItem,
  StartupConfigItem
} from "@/api/branchConfig";

const props = defineProps<{
  bp: BranchProjectItem | null;
  myRole: BranchRole;
  saving: boolean;
}>();

const emit = defineEmits<{ (e: "save", form: StartupConfigItem): void }>();

const form = reactive<StartupConfigItem>({
  command: "",
  args: [],
  env_vars: {},
  working_directory: "",
  timeout_seconds: 60,
  auto_restart: false,
  raw_json: ""
});

// 切换编辑对象时重置表单
watch(
  () => props.bp,
  bp => {
    const conf = bp?.startup_config;
    form.command = conf?.command ?? "";
    form.args = [...(conf?.args ?? [])];
    form.env_vars = { ...(conf?.env_vars ?? {}) };
    form.working_directory = conf?.working_directory ?? "";
    form.timeout_seconds = conf?.timeout_seconds ?? 60;
    form.auto_restart = conf?.auto_restart ?? false;
    form.raw_json = conf?.raw_json ?? "";
  },
  { immediate: true }
);

/** 环境变量键列表（与 form.env_vars 同步） */
const envKeys = computed(() => Object.keys(form.env_vars));

/** value 编辑：按行号回写当前键的值 */
function bindEnv(idx: number, value: string) {
  const key = envKeys.value[idx];
  if (key === undefined) return;
  form.env_vars[key] = value;
}

/** key 编辑：迁移旧键的值到新键并删除旧键（空键或目标重复时忽略） */
function renameEnv(idx: number, newKey: string) {
  const oldKey = envKeys.value[idx];
  if (!oldKey || !newKey || oldKey === newKey) return;
  if (newKey in form.env_vars) return;
  form.env_vars[newKey] = form.env_vars[oldKey];
  delete form.env_vars[oldKey];
}

function addEnv() {
  // 空键守卫：已有未填写 KEY 的空键行时不再新增（避免重复写入 env_vars[""]，R3-F11）
  if ("" in form.env_vars) return;
  form.env_vars[""] = "";
}

function removeEnv(idx: number) {
  const key = envKeys.value[idx];
  if (key !== undefined) delete form.env_vars[key];
}

/** 保存前过滤空键行：未填写 KEY 的占位行不应进入提交载荷（R3-F11） */
function onSaveClick() {
  const envVars: Record<string, string> = {};
  for (const [k, v] of Object.entries(form.env_vars)) {
    if (k.trim()) envVars[k] = v;
  }
  emit("save", { ...form, env_vars: envVars });
}
</script>

<style scoped>
.kv-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
  align-items: center;
}
.raw-json {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
