<script setup lang="ts">
// 系统管理页（仅管理员）
// 设计文档 8.6：版本分支 / 用户管理 / 策略模板 / 关键配置 四个 Tab
import { ref, reactive, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { adminApi } from "@/api/admin";
import { previewStrategy } from "@/api/strategy";
import type { PreviewResult } from "@/api/strategy";
import type {
  VersionItem,
  UserInfo,
  TemplateItem,
  GlobalConfig,
  StrategyItem
} from "@/api/types";

defineOptions({ name: "SystemIndex" });

const activeTab = ref("versions");
const loading = ref(false);

// ============ Tab1 版本分支 ============
const versions = ref<VersionItem[]>([]);
const users = ref<UserInfo[]>([]);

const roleMap: Record<string, string> = {
  admin: "管理员",
  pm: "项目经理",
  builder: "构建人员",
  tester: "防护网测试",
  integrator: "集成人员"
};

/** PM 绑定候选：pm 角色且未绑定（或绑定当前版本） */
function pmCandidates(currentVersion?: VersionItem) {
  const boundIds = versions.value
    .map(v => v.pm_user_id)
    .filter(id => id != null && id !== currentVersion?.pm_user_id);
  return users.value.filter(
    u => u.role === "pm" && !boundIds.includes(u.id)
  );
}

const versionDialog = ref(false);
const versionForm = reactive({
  id: null as number | null,
  name: "",
  pm_user_id: null as number | null,
  status: "active" as string
});

function openVersionDialog(v?: VersionItem) {
  versionDialog.value = true;
  if (v) {
    versionForm.id = v.id;
    versionForm.name = v.name;
    versionForm.pm_user_id = v.pm_user_id ?? null;
    versionForm.status = v.status;
  } else {
    versionForm.id = null;
    versionForm.name = "";
    versionForm.pm_user_id = null;
    versionForm.status = "active";
  }
}

async function saveVersion() {
  if (!versionForm.name) {
    ElMessage.warning("请输入版本名称");
    return;
  }
  if (versionForm.id) {
    await adminApi.updateVersion(versionForm.id, {
      name: versionForm.name,
      pm_user_id: versionForm.pm_user_id,
      status: versionForm.status
    });
    ElMessage.success("版本已更新");
  } else {
    await adminApi.createVersion({
      name: versionForm.name,
      pm_user_id: versionForm.pm_user_id
    });
    ElMessage.success("版本已创建");
  }
  versionDialog.value = false;
  loadVersions();
}

const branchInput = reactive<{ vid: number; name: string }>({ vid: 0, name: "" });

function openBranchInput(vid: number) {
  branchInput.vid = vid;
  branchInput.name = "";
}
async function addBranch() {
  if (!branchInput.name) {
    ElMessage.warning("请输入分支名称");
    return;
  }
  await adminApi.addBranch(branchInput.vid, branchInput.name);
  ElMessage.success("分支已添加");
  branchInput.name = "";
  loadVersions();
}

// ============ Tab2 用户管理 ============
const userDialog = ref(false);
const userForm = reactive({
  id: null as number | null,
  username: "",
  password: "",
  display_name: "",
  role: "builder" as string
});

function openUserDialog(u?: UserInfo) {
  userDialog.value = true;
  if (u) {
    userForm.id = u.id;
    userForm.username = u.username;
    userForm.password = "";
    userForm.display_name = u.display_name;
    userForm.role = u.role;
  } else {
    userForm.id = null;
    userForm.username = "";
    userForm.password = "";
    userForm.display_name = "";
    userForm.role = "builder";
  }
}

async function saveUser() {
  if (!userForm.username) {
    ElMessage.warning("请输入用户名");
    return;
  }
  if (userForm.id) {
    await adminApi.updateUser(userForm.id, {
      display_name: userForm.display_name,
      role: userForm.role,
      password: userForm.password || undefined
    });
    ElMessage.success("用户已更新");
  } else {
    if (!userForm.password) {
      ElMessage.warning("请输入初始密码");
      return;
    }
    await adminApi.createUser({
      username: userForm.username,
      password: userForm.password,
      display_name: userForm.display_name,
      role: userForm.role
    });
    ElMessage.success("用户已创建");
  }
  userDialog.value = false;
  loadUsers();
}

async function toggleUser(u: UserInfo) {
  await adminApi.updateUser(u.id, { is_active: !u.is_active });
  ElMessage.success(u.is_active ? "用户已停用" : "用户已启用");
  loadUsers();
}

async function resetPassword(u: UserInfo) {
  const { value } = await ElMessageBox.prompt(
    `重置用户 ${u.username} 的密码`,
    "重置密码",
    {
      inputType: "password",
      inputPlaceholder: "请输入新密码",
      confirmButtonText: "确认",
      cancelButtonText: "取消"
    }
  );
  await adminApi.updateUser(u.id, { password: value });
  ElMessage.success("密码已重置");
}

// ============ Tab3 策略模板 ============
const templates = ref<TemplateItem[]>([]);
const templateDialog = ref(false);
const templateForm = reactive({
  id: null as number | null,
  name: "",
  smoke_minutes: 60,
  analysis_minutes: 30,
  description: ""
});

function openTemplateDialog(t?: TemplateItem) {
  templateDialog.value = true;
  if (t) {
    templateForm.id = t.id;
    templateForm.name = t.name;
    templateForm.smoke_minutes = t.smoke_minutes;
    templateForm.analysis_minutes = t.analysis_minutes;
    templateForm.description = t.description || "";
  } else {
    templateForm.id = null;
    templateForm.name = "";
    templateForm.smoke_minutes = 60;
    templateForm.analysis_minutes = 30;
    templateForm.description = "";
  }
}

async function saveTemplate() {
  if (!templateForm.name) {
    ElMessage.warning("请输入模板名称");
    return;
  }
  if (templateForm.id) {
    await adminApi.updateTemplate(templateForm.id, {
      name: templateForm.name,
      smoke_minutes: templateForm.smoke_minutes,
      analysis_minutes: templateForm.analysis_minutes,
      description: templateForm.description
    });
    ElMessage.success("模板已更新");
  } else {
    await adminApi.createTemplate({
      name: templateForm.name,
      smoke_minutes: templateForm.smoke_minutes,
      analysis_minutes: templateForm.analysis_minutes,
      description: templateForm.description
    });
    ElMessage.success("模板已创建");
  }
  templateDialog.value = false;
  loadTemplates();
}

async function deleteTemplate(t: TemplateItem) {
  await ElMessageBox.confirm(
    `确认删除模板「${t.name}」？被策略引用的模板不可删除。`,
    "删除模板",
    { type: "warning", confirmButtonText: "确认删除", cancelButtonText: "取消" }
  );
  await adminApi.deleteTemplate(t.id);
  ElMessage.success("模板已删除");
  loadTemplates();
}

// ============ Tab4 关键配置 ============
const configForm = reactive<GlobalConfig>({
  build_minutes: 30,
  push_minutes: 20,
  sync_buffer_minutes: 20
});

async function saveConfig() {
  await adminApi.updateConfig({ ...configForm });
  ElMessage.success("关键配置已保存");
}

// ============ Tab5 策略配置（管理员全量 CRUD） ============
const adminStrategies = ref<StrategyItem[]>([]);
const adminVersionId = ref<number | undefined>(undefined);
const adminBranchId = ref<number | undefined>(undefined);
const adminStrategyDialog = ref(false);
const adminStrategyForm = reactive({
  branch_id: 0,
  template_id: 0,
  name: "",
  build_start_time: "22:00",
  push_start_time: "" as string,
  push_mode: "normal",
  enabled: true
});
const adminEditingId = ref<number | null>(null);
const adminPreview = ref<PreviewResult | null>(null);

/** 分支选项：按当前所选版本过滤 */
const adminBranchOptions = computed(() => {
  if (!adminVersionId.value) return [];
  const v = versions.value.find(x => x.id === adminVersionId.value);
  return (v?.branches || []).map(b => ({ id: b.id, name: b.name }));
});

async function loadAdminStrategies() {
  loading.value = true;
  try {
    adminStrategies.value = await adminApi.getAdminStrategies({
      version_id: adminVersionId.value,
      branch_id: adminBranchId.value
    });
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
  if (s) {
    adminEditingId.value = s.id;
    adminStrategyForm.branch_id = s.branch_id;
    adminStrategyForm.template_id = s.template_id;
    adminStrategyForm.name = s.name;
    adminStrategyForm.build_start_time = s.build_start_time;
    adminStrategyForm.push_start_time = s.push_start_time || "";
    adminStrategyForm.push_mode = s.push_mode;
    adminStrategyForm.enabled = s.enabled;
  } else {
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

let adminPreviewTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleAdminPreview() {
  if (adminPreviewTimer) clearTimeout(adminPreviewTimer);
  adminPreviewTimer = setTimeout(runAdminPreview, 400);
}
async function runAdminPreview() {
  if (!adminStrategyForm.branch_id || !adminStrategyForm.template_id) return;
  try {
    adminPreview.value = await previewStrategy({
      branch_id: adminStrategyForm.branch_id,
      template_id: adminStrategyForm.template_id,
      name: adminStrategyForm.name,
      build_start_time: adminStrategyForm.build_start_time,
      push_start_time: adminStrategyForm.push_start_time || null,
      push_mode: adminStrategyForm.push_mode,
      enabled: adminStrategyForm.enabled
    });
  } catch {
    adminPreview.value = null;
  }
}

async function saveAdminStrategy() {
  if (adminPreview.value?.conflict) {
    ElMessageBox.alert(adminPreview.value.conflict.message || "存在时间冲突", "策略时间冲突", {
      type: "error",
      confirmButtonText: "知道了"
    });
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
  if (adminEditingId.value) {
    await adminApi.updateAdminStrategy(adminEditingId.value, payload);
    ElMessage.success("策略已更新");
  } else {
    await adminApi.createAdminStrategy(payload);
    ElMessage.success("策略已创建");
  }
  adminStrategyDialog.value = false;
  loadAdminStrategies();
}

// 注意：adminApi.toggleAdminStrategy 是无参翻转语义（后端翻转 enabled），切不可传 enabled 参数
async function toggleAdminStrategy(s: StrategyItem) {
  await adminApi.toggleAdminStrategy(s.id);
  ElMessage.success(s.enabled ? "策略已启用" : "策略已停用");
  loadAdminStrategies();
}

async function deleteAdminStrategy(s: StrategyItem) {
  await ElMessageBox.confirm(
    `确认删除策略「${s.name}」？将级联清理其关联执行数据。`,
    "删除策略",
    { type: "warning", confirmButtonText: "确认删除", cancelButtonText: "取消" }
  );
  await adminApi.deleteAdminStrategy(s.id);
  ElMessage.success("策略已删除");
  loadAdminStrategies();
}

// ============ 加载 ============
async function loadVersions() {
  versions.value = await adminApi.getVersions();
}
async function loadUsers() {
  users.value = await adminApi.getUsers();
}
async function loadTemplates() {
  templates.value = await adminApi.getTemplates();
}
async function loadConfig() {
  const cfg = await adminApi.getConfig();
  Object.assign(configForm, cfg);
}

onMounted(async () => {
  await Promise.all([loadVersions(), loadUsers(), loadTemplates(), loadConfig(), loadAdminStrategies()]);
});
</script>

<template>
  <div class="admin-page">
    <el-tabs v-model="activeTab">
      <!-- Tab1 版本分支 -->
      <el-tab-pane label="版本分支" name="versions">
        <div class="toolbar">
          <el-button type="primary" size="small" @click="openVersionDialog()">
            新增版本
          </el-button>
        </div>
        <el-table :data="versions" style="width: 100%">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="branch-panel">
                <div class="branch-title">分支列表</div>
                <div class="branch-items">
                  <el-tag
                    v-for="b in row.branches"
                    :key="b.id"
                    class="branch-tag"
                  >
                    {{ b.name }}
                  </el-tag>
                </div>
                <div class="branch-add">
                  <el-input
                    v-if="branchInput.vid === row.id"
                    v-model="branchInput.name"
                    size="small"
                    placeholder="分支名称"
                    style="width: 180px"
                    @keyup.enter="addBranch"
                  />
                  <el-button
                    v-if="branchInput.vid === row.id"
                    size="small"
                    type="primary"
                    @click="addBranch"
                  >
                    保存
                  </el-button>
                  <el-button
                    v-if="branchInput.vid === row.id"
                    size="small"
                    @click="branchInput.vid = 0"
                  >
                    取消
                  </el-button>
                  <el-button
                    v-else
                    size="small"
                    @click="openBranchInput(row.id)"
                  >
                    + 添加分支
                  </el-button>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="版本" width="140" />
          <el-table-column prop="pm_name" label="PM" min-width="140">
            <template #default="{ row }">{{ row.pm_name || "未绑定" }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
                {{ row.status === "active" ? "启用" : "归档" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="openVersionDialog(row)">
                编辑
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab2 用户管理 -->
      <el-tab-pane label="用户管理" name="users">
        <div class="toolbar">
          <el-button type="primary" size="small" @click="openUserDialog()">
            新建用户
          </el-button>
        </div>
        <el-table :data="users" style="width: 100%">
          <el-table-column prop="username" label="用户名" width="140" />
          <el-table-column prop="display_name" label="显示名" min-width="140" />
          <el-table-column label="角色" width="120">
            <template #default="{ row }">{{ roleMap[row.role] || row.role }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_active === false ? 'info' : 'success'" size="small">
                {{ row.is_active === false ? "停用" : "启用" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="openUserDialog(row)">编辑</el-button>
              <el-button size="small" link @click="resetPassword(row)">重置密码</el-button>
              <el-button size="small" link @click="toggleUser(row)">
                {{ row.is_active === false ? "启用" : "停用" }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab3 策略模板 -->
      <el-tab-pane label="策略模板" name="templates">
        <div class="toolbar">
          <el-button type="primary" size="small" @click="openTemplateDialog()">
            新增模板
          </el-button>
        </div>
        <el-table :data="templates" style="width: 100%">
          <el-table-column prop="name" label="模板名称" min-width="160" />
          <el-table-column label="冒烟耗时" width="120">
            <template #default="{ row }">{{ row.smoke_minutes }} 分钟</template>
          </el-table-column>
          <el-table-column label="分析耗时" width="120">
            <template #default="{ row }">{{ row.analysis_minutes }} 分钟</template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="180" />
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="openTemplateDialog(row)">编辑</el-button>
              <el-button type="danger" link size="small" @click="deleteTemplate(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab4 关键配置 -->
      <el-tab-pane label="关键配置" name="config">
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
      </el-tab-pane>

      <!-- Tab5 策略配置（管理员全量） -->
      <el-tab-pane label="策略配置" name="strategies">
        <div class="toolbar">
          <el-select v-model="adminVersionId" placeholder="全部版本" clearable style="width: 160px" @change="onAdminVersionChange">
            <el-option v-for="v in versions" :key="v.id" :label="v.name" :value="v.id" />
          </el-select>
          <el-select v-model="adminBranchId" placeholder="全部分支" clearable style="width: 160px" :disabled="!adminVersionId" @change="loadAdminStrategies">
            <el-option v-for="b in adminBranchOptions" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
          <el-button type="primary" size="small" @click="loadAdminStrategies">查询</el-button>
          <el-button type="primary" size="small" @click="openAdminStrategy()">新建策略</el-button>
        </div>
        <el-table :data="adminStrategies" v-loading="loading" style="width: 100%">
          <el-table-column prop="name" label="策略名称" min-width="180" />
          <el-table-column prop="version_name" label="版本" width="90" />
          <el-table-column prop="branch_name" label="分支" width="100" />
          <el-table-column prop="template_name" label="模板" width="120" />
          <el-table-column prop="build_start_time" label="构建开始" width="100" />
          <el-table-column label="推送" width="110">
            <template #default="{ row }"> {{ row.push_start_time || "结论后推导" }} </template>
          </el-table-column>
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" @change="toggleAdminStrategy(row as StrategyItem)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="openAdminStrategy(row as StrategyItem)">编辑</el-button>
              <el-button type="danger" link size="small" @click="deleteAdminStrategy(row as StrategyItem)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 策略编辑弹窗（管理员） -->
    <el-dialog v-model="adminStrategyDialog" :title="adminEditingId ? '编辑策略' : '新建策略'" width="480px">
      <el-form :model="adminStrategyForm" label-width="110px">
        <el-form-item label="策略分支">
          <el-select v-model="adminStrategyForm.branch_id" style="width: 100%" @change="scheduleAdminPreview">
            <el-option v-for="b in adminBranchOptions" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="策略模板">
          <el-select v-model="adminStrategyForm.template_id" style="width: 100%" @change="scheduleAdminPreview">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="策略名称">
          <el-input v-model="adminStrategyForm.name" placeholder="策略名称" />
        </el-form-item>
        <el-form-item label="构建开始时间">
          <el-time-picker v-model="adminStrategyForm.build_start_time" value-format="HH:mm" format="HH:mm" style="width: 160px" @change="scheduleAdminPreview" />
        </el-form-item>
        <el-form-item label="推送时间（可空）">
          <el-time-picker v-model="adminStrategyForm.push_start_time" value-format="HH:mm" format="HH:mm" placeholder="留空=结论后推导" clearable style="width: 160px" @change="scheduleAdminPreview" />
        </el-form-item>
        <el-form-item label="推送模式">
          <el-radio-group v-model="adminStrategyForm.push_mode" @change="scheduleAdminPreview">
            <el-radio value="normal">正常流程推送</el-radio>
            <el-radio value="sync">同步推送冒烟</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="adminStrategyForm.enabled" />
        </el-form-item>
        <el-form-item v-if="adminPreview?.conflict" label="冲突">
          <span class="preview-conflict"> {{ adminPreview.conflict.message || "存在时间冲突" }} </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adminStrategyDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!!adminPreview?.conflict" @click="saveAdminStrategy">保存</el-button>
      </template>
    </el-dialog>

    <!-- 版本弹窗 -->
    <el-dialog
      v-model="versionDialog"
      :title="versionForm.id ? '编辑版本' : '新增版本'"
      width="440px"
    >
      <el-form label-width="80px">
        <el-form-item label="版本名称">
          <el-input v-model="versionForm.name" placeholder="如 28A" />
        </el-form-item>
        <el-form-item label="绑定 PM">
          <el-select
            v-model="versionForm.pm_user_id"
            clearable
            placeholder="仅显示未绑定版本的 PM"
            style="width: 100%"
          >
            <el-option
              v-for="u in pmCandidates(versions.find(v => v.id === versionForm.id))"
              :key="u.id"
              :label="`${u.display_name}（${u.username}）`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="versionForm.id" label="状态">
          <el-radio-group v-model="versionForm.status">
            <el-radio value="active">启用</el-radio>
            <el-radio value="archived">归档</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="versionDialog = false">取消</el-button>
        <el-button type="primary" @click="saveVersion">保存</el-button>
      </template>
    </el-dialog>

    <!-- 用户弹窗 -->
    <el-dialog
      v-model="userDialog"
      :title="userForm.id ? '编辑用户' : '新建用户'"
      width="440px"
    >
      <el-form label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="userForm.username" :disabled="!!userForm.id" />
        </el-form-item>
        <el-form-item :label="userForm.id ? '重置密码' : '初始密码'">
          <el-input
            v-model="userForm.password"
            type="password"
            :placeholder="userForm.id ? '留空则不修改' : '请输入初始密码'"
            show-password
          />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="userForm.display_name" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="userForm.role" style="width: 100%">
            <el-option v-for="(l, r) in roleMap" :key="r" :label="l" :value="r" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDialog = false">取消</el-button>
        <el-button type="primary" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>

    <!-- 模板弹窗 -->
    <el-dialog
      v-model="templateDialog"
      :title="templateForm.id ? '编辑模板' : '新增模板'"
      width="440px"
    >
      <el-form label-width="90px">
        <el-form-item label="模板名称">
          <el-input v-model="templateForm.name" placeholder="如 晚间全量冒烟" />
        </el-form-item>
        <el-form-item label="冒烟耗时（分）">
          <el-input-number v-model="templateForm.smoke_minutes" :min="1" />
        </el-form-item>
        <el-form-item label="分析耗时（分）">
          <el-input-number v-model="templateForm.analysis_minutes" :min="1" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="templateForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="templateDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTemplate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-page {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}
.toolbar {
  margin-bottom: 12px;
}
.branch-panel {
  padding: 8px 24px;
}
.branch-title {
  color: #909399;
  font-size: 13px;
  margin-bottom: 8px;
}
.branch-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.branch-add {
  display: flex;
  align-items: center;
  gap: 8px;
}
.config-form {
  max-width: 420px;
}
.preview-conflict {
  color: #ef4444;
  font-size: 13px;
}
</style>