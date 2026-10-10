<script setup lang="ts">
// 系统管理 - 关键配置 Tab：构建/推送/同步缓冲耗时（后端落库持久化）
import { onMounted, reactive } from "vue";
import { ElMessage } from "element-plus";
import { adminApi } from "@/api/admin";
import type { GlobalConfig } from "@/api/types";

defineOptions({ name: "AdminConfigTab" });

const configForm = reactive<GlobalConfig>({
  build_minutes: 30,
  push_minutes: 20,
  sync_buffer_minutes: 20
});

async function loadConfig() {
  const cfg = await adminApi.getConfig();
  Object.assign(configForm, cfg);
}

async function saveConfig() {
  await adminApi.updateConfig({ ...configForm });
  ElMessage.success("关键配置已保存");
}

onMounted(loadConfig);
</script>

<template>
  <el-form :model="configForm" label-width="140px" class="config-form">
    <el-form-item label="构建耗时（分钟）">
      <el-input-number v-model="configForm.build_minutes" :min="1" />
    </el-form-item>
    <el-form-item label="推送耗时（分钟）">
      <el-input-number v-model="configForm.push_minutes" :min="1" />
    </el-form-item>
    <el-form-item label="同步缓冲（分钟）">
      <el-input-number v-model="configForm.sync_buffer_minutes" :min="1" />
    </el-form-item>
    <el-form-item>
      <el-button type="primary" @click="saveConfig">保存配置</el-button>
    </el-form-item>
  </el-form>
</template>

<style scoped>
.config-form {
  max-width: 420px;
}
</style>
