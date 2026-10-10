<script setup lang="ts">
// 系统管理 - 用户管理 Tab：用户列表/新建编辑/重置密码/启停
import { reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { adminApi } from "@/api/admin";
import type { UserInfo } from "@/api/types";
import { roleTextMap } from "@/views/constants";

defineOptions({ name: "AdminUsersTab" });

const props = defineProps<{
  users: UserInfo[];
}>();

const emit = defineEmits<{ refresh: [] }>();

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
  emit("refresh");
}

async function toggleUser(u: UserInfo) {
  await adminApi.updateUser(u.id, { is_active: !u.is_active });
  ElMessage.success(u.is_active ? "用户已停用" : "用户已启用");
  emit("refresh");
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
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" size="small" @click="openUserDialog()">
        新建用户
      </el-button>
    </div>
    <el-table :data="users" style="width: 100%">
      <el-table-column prop="username" label="用户名" width="140" />
      <el-table-column prop="display_name" label="显示名" min-width="140" />
      <el-table-column label="角色" width="120">
        <template #default="{ row }">{{ roleTextMap[row.role] || row.role }}</template>
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
          <el-button type="primary" link size="small" @click="openUserDialog(row as UserInfo)">编辑</el-button>
          <el-button size="small" link @click="resetPassword(row as UserInfo)">重置密码</el-button>
          <el-button size="small" link @click="toggleUser(row as UserInfo)">
            {{ row.is_active === false ? "启用" : "停用" }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

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
            <el-option
              v-for="(l, r) in roleTextMap"
              :key="r"
              :label="l"
              :value="r"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDialog = false">取消</el-button>
        <el-button type="primary" @click="saveUser">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  margin-bottom: 12px;
}
</style>
