<script setup lang="ts">
// 系统管理 - 版本分支 Tab：版本列表/新增编辑 + 展开行内添加分支
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { adminApi } from "@/api/admin";
import type { UserInfo, VersionItem } from "@/api/types";

defineOptions({ name: "AdminVersionsTab" });

const props = defineProps<{
  versions: VersionItem[];
  users: UserInfo[];
}>();

const emit = defineEmits<{ refresh: [] }>();

/** PM 绑定候选：pm 角色且未绑定（或绑定当前版本） */
function pmCandidates(currentVersion?: VersionItem) {
  const boundIds = props.versions
    .map(v => v.pm_user_id)
    .filter(id => id != null && id !== currentVersion?.pm_user_id);
  return props.users.filter(u => u.role === "pm" && !boundIds.includes(u.id));
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
  emit("refresh");
}

const branchInput = reactive<{ vid: number; name: string }>({
  vid: 0,
  name: ""
});

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
  emit("refresh");
}
</script>

<template>
  <div>
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
              <el-tag v-for="b in row.branches" :key="b.id" class="branch-tag">
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
              <el-button v-else size="small" @click="openBranchInput(row.id)">
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
          <el-tag
            :type="row.status === 'active' ? 'success' : 'info'"
            size="small"
          >
            {{ row.status === "active" ? "启用" : "归档" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            size="small"
            @click="openVersionDialog(row as VersionItem)"
          >
            编辑
          </el-button>
        </template>
      </el-table-column>
    </el-table>

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
              v-for="u in pmCandidates(
                versions.find(v => v.id === versionForm.id)
              )"
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
  </div>
</template>

<style scoped>
.toolbar {
  margin-bottom: 12px;
}
.branch-panel {
  padding: 8px 24px;
}
.branch-title {
  color: var(--el-text-color-secondary);
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
</style>
