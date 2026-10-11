<script setup lang="ts">
// 系统管理页（仅管理员）：五个 Tab 由子组件承载，本组件持有跨 Tab 共享数据
// 设计文档 8.6：版本分支 / 用户管理 / 策略模板 / 关键配置 / 策略配置
import { onMounted, ref } from "vue";
import { adminApi } from "@/api/admin";
import VersionsTab from "./components/VersionsTab.vue";
import UsersTab from "./components/UsersTab.vue";
import TemplatesTab from "./components/TemplatesTab.vue";
import ConfigTab from "./components/ConfigTab.vue";
import StrategiesTab from "./components/StrategiesTab.vue";
import type { TemplateItem, UserInfo, VersionItem } from "@/api/types";

defineOptions({ name: "SystemIndex" });

const activeTab = ref("versions");

// ---- 跨 Tab 共享数据：版本（Tab1/Tab5）、用户（Tab1/Tab2）、模板（Tab3/Tab5）----
const versions = ref<VersionItem[]>([]);
const users = ref<UserInfo[]>([]);
const templates = ref<TemplateItem[]>([]);

async function loadVersions() {
  versions.value = await adminApi.getVersions();
}
async function loadUsers() {
  users.value = await adminApi.getUsers();
}
async function loadTemplates() {
  templates.value = await adminApi.getTemplates();
}

onMounted(async () => {
  await Promise.all([loadVersions(), loadUsers(), loadTemplates()]);
});
</script>

<template>
  <div class="admin-page biz-card">
    <el-tabs v-model="activeTab">
      <!-- Tab1 版本分支 -->
      <el-tab-pane label="版本分支" name="versions">
        <VersionsTab :versions="versions" :users="users" @refresh="loadVersions" />
      </el-tab-pane>

      <!-- Tab2 用户管理 -->
      <el-tab-pane label="用户管理" name="users">
        <UsersTab :users="users" @refresh="loadUsers" />
      </el-tab-pane>

      <!-- Tab3 策略模板 -->
      <el-tab-pane label="策略模板" name="templates">
        <TemplatesTab :templates="templates" @refresh="loadTemplates" />
      </el-tab-pane>

      <!-- Tab4 关键配置 -->
      <el-tab-pane label="关键配置" name="config">
        <ConfigTab />
      </el-tab-pane>

      <!-- Tab5 策略配置（管理员全量） -->
      <el-tab-pane label="策略配置" name="strategies">
        <StrategiesTab :versions="versions" :templates="templates" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
/* 页面容器复用全局 .biz-card */
</style>
