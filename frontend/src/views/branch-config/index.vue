<template>
  <div class="branch-config">
    <!-- 左侧：分支列表 -->
    <aside class="branch-side">
      <div class="side-toolbar">
        <el-input
          v-model="keyword"
          size="small"
          placeholder="搜索分支"
          clearable
          style="flex: 1"
        />
        <el-button size="small" type="primary" @click="openNewDialog"
          >＋ 新建</el-button
        >
      </div>
      <div class="branch-list">
        <div
          v-for="b in filteredBranches"
          :key="b.id"
          class="branch-item"
          :class="{ active: b.id === selectedId }"
          @click="selectBranch(b.id)"
        >
          <div class="branch-name">{{ b.version_name }} / {{ b.name }}</div>
          <div v-if="b.repository_url" class="branch-url">
            {{ b.repository_url }}
          </div>
        </div>
        <el-empty
          v-if="!filteredBranches.length"
          description="暂无分支，点击新建"
          :image-size="60"
        />
      </div>
    </aside>

    <!-- 右侧：详情 -->
    <section class="branch-detail">
      <template v-if="config">
        <!-- 权限面板 -->
        <div class="perm-bar">
          <span class="perm-title">权限</span>
          <el-tag
            v-for="p in config.permissions"
            :key="p.id"
            :type="permTagType(p.role)"
            size="small"
            :closable="config.my_role === 'ADMIN'"
            @close="removePermission(p)"
          >
            {{ p.username }} · {{ permLabel(p.role) }}
          </el-tag>
          <el-button
            v-if="config.my_role === 'ADMIN'"
            size="small"
            text
            type="primary"
            @click="permDialogVisible = true"
          >
            ＋ 添加授权
          </el-button>
          <span class="perm-myrole"
            >我的角色：{{ permLabel(config.my_role) }}</span
          >
        </div>

        <el-tabs v-model="activeTab" class="detail-tabs">
          <el-tab-pane label="工程关联" name="projects">
            <ProjectsPanel
              :items="config.branch_projects"
              :my-role="config.my_role"
              :available-projects="config.available_projects"
              :adding="addingProject"
              @add="addProject"
              @remove="removeProject"
              @edit-config="editConfig"
              @start="startInstance"
              @stop="stopInstance"
            />
          </el-tab-pane>
          <el-tab-pane label="启动参数" name="config">
            <StartupConfigForm
              :bp="editingBp"
              :my-role="config.my_role"
              :saving="savingConfig"
              @save="saveConfig"
            />
          </el-tab-pane>
          <el-tab-pane label="运行状态" name="instances">
            <InstancesPanel
              :rows="instanceRows"
              :my-role="config.my_role"
              :starting-id="startingId"
              :stopping-id="stoppingId"
              @start="startInstance"
              @stop="stopInstance"
            />
          </el-tab-pane>
        </el-tabs>
      </template>
      <el-empty v-else description="请选择左侧分支" />
    </section>

    <!-- 新建分支 -->
    <el-dialog v-model="newDialogVisible" title="新建分支" width="440px">
      <el-form label-width="80px" size="small">
        <el-form-item label="版本">
          <el-select
            v-model="newForm.version_id"
            filterable
            placeholder="选择版本"
            style="width: 100%"
          >
            <el-option
              v-for="v in versionOptions"
              :key="v.version_id"
              :label="v.version_name"
              :value="v.version_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="分支名">
          <el-input v-model="newForm.name" placeholder="如 master / TR5" />
        </el-form-item>
        <el-form-item label="仓库地址">
          <el-input
            v-model="newForm.repository_url"
            placeholder="可选，如 https://git.local/27A.git"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="creatingBranch"
          @click="createBranch"
          >创建</el-button
        >
      </template>
    </el-dialog>

    <!-- 添加授权 -->
    <el-dialog v-model="permDialogVisible" title="添加授权" width="420px">
      <el-form label-width="60px" size="small">
        <el-form-item label="用户">
          <el-select
            v-model="permForm.user_id"
            filterable
            placeholder="选择用户"
            style="width: 100%"
          >
            <el-option
              v-for="u in config?.available_users ?? []"
              :key="u.id"
              :label="`${u.username}（${u.display_name || u.role}）`"
              :value="u.id"
              :disabled="grantedUserIds.includes(u.id)"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="permForm.role">
            <el-radio value="VIEWER">查看者</el-radio>
            <el-radio value="OPERATOR">操作者</el-radio>
            <el-radio value="ADMIN">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="permDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingPerm" @click="savePermission"
          >确定</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getPlan } from "@/api/plan";
import {
  addBranchPermission,
  addBranchProject,
  createBranch as apiCreateBranch,
  deleteBranch,
  getBranches,
  getBranchConfig,
  getBranchInstances,
  removeBranchPermission,
  removeBranchProject,
  startBranchProject,
  stopBranchProject,
  updateStartupConfig,
  type BranchConfigResponse,
  type BranchItem,
  type BranchProjectItem,
  type BranchRole,
  type InstanceRow,
  type PermissionItem,
  type StartupConfigItem
} from "@/api/branchConfig";
import ProjectsPanel from "./components/ProjectsPanel.vue";
import StartupConfigForm from "./components/StartupConfigForm.vue";
import InstancesPanel from "./components/InstancesPanel.vue";

// ---------- 分支列表 ----------
const branches = ref<BranchItem[]>([]);
const selectedId = ref<number | null>(null);
const keyword = ref("");
const config = ref<BranchConfigResponse>();
const loadingConfig = ref(false);

const filteredBranches = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return branches.value;
  return branches.value.filter(
    b =>
      b.name.toLowerCase().includes(kw) ||
      b.version_name.toLowerCase().includes(kw)
  );
});

async function loadBranches() {
  branches.value = await getBranches();
  if (!selectedId.value && branches.value.length) {
    selectedId.value = branches.value[0].id;
  }
  if (!branches.value.length) {
    config.value = undefined;
  }
}

async function selectBranch(id: number) {
  if (selectedId.value === id) return;
  selectedId.value = id;
  await loadConfig();
}

async function loadConfig() {
  if (!selectedId.value) return;
  loadingConfig.value = true;
  try {
    config.value = await getBranchConfig(selectedId.value);
    editingBp.value = config.value.branch_projects[0] ?? null;
    activeTab.value = "projects";
  } finally {
    loadingConfig.value = false;
  }
}

// ---------- 实例轮询（仅当前分支，5s） ----------
const instanceRows = ref<InstanceRow[]>([]);
let pollTimer: number | null = null;
// 过期响应守卫：切分支时作废在途请求，防止 A 分支的响应晚于 B 返回、
// 把 B 的实例列表覆盖成 A 的（视图与数据错配，要等下一轮轮询才被纠正）
let pollSeq = 0;

async function pollInstances() {
  const branchId = selectedId.value;
  if (!branchId) return;
  const cur = ++pollSeq;
  try {
    const rows = await getBranchInstances(branchId);
    if (cur === pollSeq && branchId === selectedId.value) {
      instanceRows.value = rows;
    }
  } catch {
    /* 轮询失败静默，等待下一周期 */
  }
}

watch(selectedId, id => {
  // 主动作废所有在途请求
  pollSeq++;
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
  if (id) {
    pollInstances();
    pollTimer = window.setInterval(pollInstances, 5000);
  }
});

onBeforeUnmount(() => {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
});

// ---------- 新建分支 ----------
const newDialogVisible = ref(false);
const creatingBranch = ref(false);
const newForm = reactive<{
  version_id: number | undefined;
  name: string;
  repository_url: string;
}>({
  version_id: undefined,
  name: "",
  repository_url: ""
});
const versionOptions = ref<{ version_id: number; version_name: string }[]>([]);

async function openNewDialog() {
  const today = new Date().toISOString().slice(0, 10);
  try {
    const plan = await getPlan({ date: today });
    versionOptions.value = plan.map(p => ({
      version_id: p.version_id,
      version_name: p.version_name
    }));
  } catch {
    versionOptions.value = [];
  }
  newForm.version_id = versionOptions.value[0]?.version_id;
  newForm.name = "";
  newForm.repository_url = "";
  newDialogVisible.value = true;
}

async function createBranch() {
  if (!newForm.version_id || !newForm.name.trim()) {
    ElMessage.warning("请选择版本并填写分支名");
    return;
  }
  creatingBranch.value = true;
  try {
    const created = await apiCreateBranch({
      version_id: newForm.version_id,
      name: newForm.name.trim(),
      repository_url: newForm.repository_url.trim() || undefined
    });
    ElMessage.success("分支已创建");
    newDialogVisible.value = false;
    branches.value.push(created);
    selectedId.value = created.id;
    await loadConfig();
  } finally {
    creatingBranch.value = false;
  }
}

// ---------- 工程关联 ----------
const addingProject = ref(false);

async function addProject(projectId: number) {
  if (!selectedId.value) return;
  addingProject.value = true;
  try {
    await addBranchProject(selectedId.value, {
      project_id: projectId,
      enabled: true
    });
    ElMessage.success("工程已关联");
    await loadConfig();
  } finally {
    addingProject.value = false;
  }
}

async function removeProject(bpId: number) {
  try {
    await ElMessageBox.confirm(
      "移除该工程关联？其启动配置与实例记录将一并删除",
      "提示",
      {
        type: "warning"
      }
    );
  } catch {
    return; // 用户取消
  }
  await removeBranchProject(bpId);
  ElMessage.success("工程关联已移除");
  await loadConfig();
}

// ---------- 启动参数 ----------
const activeTab = ref("projects");
const editingBp = ref<BranchProjectItem | null>(null);
const savingConfig = ref(false);

function editConfig(bp: BranchProjectItem) {
  editingBp.value = bp;
  activeTab.value = "config";
}

async function saveConfig(form: StartupConfigItem) {
  if (!editingBp.value) return;
  savingConfig.value = true;
  try {
    await updateStartupConfig(editingBp.value.id, {
      command: form.command,
      args: form.args,
      env_vars: form.env_vars,
      working_directory: form.working_directory,
      timeout_seconds: form.timeout_seconds,
      auto_restart: form.auto_restart
    });
    ElMessage.success("启动参数已保存");
    await loadConfig();
  } finally {
    savingConfig.value = false;
  }
}

// ---------- 启停 ----------
const startingId = ref<number | null>(null);
const stoppingId = ref<number | null>(null);

async function startInstance(bpId: number) {
  startingId.value = bpId;
  try {
    const inst = await startBranchProject(bpId);
    ElMessage.success(`已发起启动（pid=${inst.pid}）`);
    await refreshAfterOp();
  } finally {
    startingId.value = null;
  }
}

async function stopInstance(bpId: number) {
  stoppingId.value = bpId;
  try {
    await stopBranchProject(bpId);
    ElMessage.success("已发起停止");
    await refreshAfterOp();
  } finally {
    stoppingId.value = null;
  }
}

async function refreshAfterOp() {
  await loadConfig();
  await pollInstances();
}

// ---------- 授权 ----------
const permDialogVisible = ref(false);
const savingPerm = ref(false);
const permForm = reactive<{ user_id: number | undefined; role: BranchRole }>({
  user_id: undefined,
  role: "OPERATOR"
});

const grantedUserIds = computed(() =>
  (config.value?.permissions ?? []).map(p => p.user_id)
);

async function savePermission() {
  if (!selectedId.value || !permForm.user_id) {
    ElMessage.warning("请选择用户");
    return;
  }
  savingPerm.value = true;
  try {
    await addBranchPermission(selectedId.value, {
      user_id: permForm.user_id,
      role: permForm.role
    });
    ElMessage.success("授权已保存");
    permDialogVisible.value = false;
    await loadConfig();
  } finally {
    savingPerm.value = false;
  }
}

async function removePermission(perm: PermissionItem) {
  try {
    await ElMessageBox.confirm(`移除用户 ${perm.username} 的授权？`, "提示", {
      type: "warning"
    });
  } catch {
    return;
  }
  await removeBranchPermission(perm.id);
  ElMessage.success("授权已移除");
  await loadConfig();
}

// ---------- 权限文案 ----------
const ROLE_LABEL: Record<BranchRole, string> = {
  VIEWER: "查看者",
  OPERATOR: "操作者",
  ADMIN: "管理员"
};
const ROLE_TAG: Record<BranchRole, "info" | "primary" | "warning"> = {
  VIEWER: "info",
  OPERATOR: "primary",
  ADMIN: "warning"
};
function permLabel(r: BranchRole): string {
  return ROLE_LABEL[r] ?? r;
}
function permTagType(r: BranchRole): "info" | "primary" | "warning" {
  return ROLE_TAG[r] ?? "info";
}
</script>

<style scoped>
.branch-config {
  display: flex;
  gap: 12px;
  height: 100%;
  min-height: 520px;
}
.branch-side {
  width: 30%;
  min-width: 220px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #fff;
}
.side-toolbar {
  display: flex;
  gap: 8px;
}
.branch-list {
  flex: 1;
  overflow: auto;
}
.branch-item {
  padding: 8px 10px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid transparent;
}
.branch-item:hover {
  background: var(--el-fill-color-light);
}
.branch-item.active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
}
.branch-name {
  font-size: 14px;
  font-weight: 600;
}
.branch-url {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.branch-detail {
  flex: 1;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 12px;
  background: #fff;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.perm-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.perm-title {
  font-weight: 600;
  font-size: 14px;
}
.perm-myrole {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.detail-tabs {
  flex: 1;
}
</style>
