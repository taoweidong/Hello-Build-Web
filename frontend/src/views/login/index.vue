<script setup lang="ts">
import Motion from "./utils/motion";
import { useRouter } from "vue-router";
import { message } from "@/utils/message";
import { loginRules } from "./utils/rule";
import { ref, reactive, toRaw } from "vue";
import { debounce } from "@pureadmin/utils";
import { useNav } from "@/layout/hooks/useNav";
import { useEventListener } from "@vueuse/core";
import type { FormInstance } from "element-plus";
import { useLayout } from "@/layout/hooks/useLayout";
import { useUserStoreHook } from "@/store/modules/user";
import { isBizError } from "@/api/http";
import { initRouter, getTopMenu } from "@/router/utils";
import { bg, avatar, illustration } from "./utils/static";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";

import dayIcon from "@/assets/svg/day.svg?component";
import darkIcon from "@/assets/svg/dark.svg?component";
import Lock from "~icons/ri/lock-fill";
import User from "~icons/ri/user-3-fill";

defineOptions({
  name: "Login"
});

const router = useRouter();
const loading = ref(false);
const disabled = ref(false);
const ruleFormRef = ref<FormInstance>();

const { initStorage } = useLayout();
initStorage();

const { dataTheme, overallStyle, dataThemeChange } = useDataThemeChange();
dataThemeChange(overallStyle.value);
const { title } = useNav();

// 快速登录仅开发环境可用（演示账号密码均为 seed 口令，生产构建不展示）
const isDev = import.meta.env.DEV;

const ruleForm = reactive({
  // 仅开发环境预填演示账号，生产构建不携带默认口令
  username: import.meta.env.DEV ? "admin" : "",
  password: import.meta.env.DEV ? "123456" : ""
});

const onLogin = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  const valid = await formEl.validate().catch(() => false);
  if (!valid) return;
  loading.value = true;
  try {
    const res = await useUserStoreHook().loginByUsername({
      username: ruleForm.username,
      password: ruleForm.password
    });
    if (!res.success) {
      // 业务层已判定失败（如响应结构异常），补一条明确提示
      message("登录失败", { type: "error" });
      return;
    }
    // 获取后端路由
    await initRouter();
    disabled.value = true;
    await router.push(getTopMenu(true).path);
    message("登录成功", { type: "success" });
  } catch (e) {
    // http 拦截器已对契约内错误（BizError）弹提示，此处仅兜底非契约异常；
    // isBizError 类型守卫收窄 unknown，替代 catch (e: any)（R3-F9）
    if (!isBizError(e)) {
      message((e instanceof Error && e.message) || "登录失败，请检查账号密码", {
        type: "error"
      });
    }
  } finally {
    disabled.value = false;
    loading.value = false;
  }
};

// 回车触发登录：debounce 返回值类型要求无参，故用显式类型的包装函数
const immediateDebounce = debounce(
  () => onLogin(ruleFormRef.value),
  1000,
  true
);

useEventListener(document, "keydown", ({ code }) => {
  if (
    ["Enter", "NumpadEnter"].includes(code) &&
    !disabled.value &&
    !loading.value
  )
    immediateDebounce();
});

// ---- 开发阶段快速登录：一键填充演示账号并登录（生产构建不渲染、口令字面量随死代码被摇树） ----
interface QuickAccount {
  username: string;
  label: string;
  role: string;
}

interface QuickGroup {
  title: string;
  /** el-button 语义类型联合（R4-F14：模板处不再 `as any` 逃逸类型检查） */
  color: "primary" | "success" | "info" | "warning" | "danger";
  accounts: QuickAccount[];
}

const quickGroups: QuickGroup[] = isDev
  ? [
      {
        title: "管理",
        color: "danger",
        accounts: [{ username: "admin", label: "管理员", role: "admin" }]
      },
      {
        title: "版本负责人",
        color: "warning",
        accounts: [
          { username: "pm27a", label: "27A", role: "pm" },
          { username: "pm27b", label: "27B", role: "pm" },
          { username: "pm26b", label: "26B", role: "pm" }
        ]
      },
      {
        title: "执行",
        color: "primary",
        accounts: [
          { username: "builder", label: "构建", role: "builder" },
          { username: "tester", label: "测试", role: "tester" },
          { username: "integrator", label: "集成", role: "integrator" }
        ]
      }
    ]
  : [];

async function onQuickLogin(username: string) {
  if (!isDev) return;
  ruleForm.username = username;
  ruleForm.password = "123456";
  await onLogin(ruleFormRef.value);
}
</script>

<template>
  <div class="select-none">
    <img :src="bg" class="wave" />
    <div class="flex-c absolute right-5 top-3">
      <!-- 主题 -->
      <el-switch
        v-model="dataTheme"
        inline-prompt
        :active-icon="dayIcon"
        :inactive-icon="darkIcon"
        @change="dataThemeChange"
      />
    </div>
    <div class="login-container">
      <div class="img">
        <component :is="toRaw(illustration)" />
      </div>
      <div class="login-box">
        <div class="login-form">
          <avatar class="avatar" />
          <Motion>
            <h2 class="outline-hidden">{{ title }}</h2>
          </Motion>

          <el-form
            ref="ruleFormRef"
            :model="ruleForm"
            :rules="loginRules"
            size="large"
          >
            <Motion :delay="100">
              <el-form-item
                :rules="[
                  {
                    required: true,
                    message: '请输入账号',
                    trigger: 'blur'
                  }
                ]"
                prop="username"
              >
                <el-input
                  v-model="ruleForm.username"
                  clearable
                  placeholder="账号"
                  :prefix-icon="useRenderIcon(User)"
                />
              </el-form-item>
            </Motion>

            <Motion :delay="150">
              <el-form-item prop="password">
                <el-input
                  v-model="ruleForm.password"
                  clearable
                  show-password
                  placeholder="密码"
                  :prefix-icon="useRenderIcon(Lock)"
                />
              </el-form-item>
            </Motion>

            <Motion :delay="250">
              <el-button
                class="w-full mt-4!"
                size="default"
                type="primary"
                :loading="loading"
                :disabled="disabled"
                @click="onLogin(ruleFormRef)"
              >
                登录
              </el-button>
            </Motion>

            <!-- 开发阶段快速登录：按角色分组一键切换演示账号（生产构建不渲染） -->
            <Motion :delay="300">
              <div v-if="isDev" class="quick-login">
                <div
                  v-for="group in quickGroups"
                  :key="group.title"
                  class="quick-group"
                >
                  <span class="quick-group-title">{{ group.title }}</span>
                  <div class="quick-group-buttons">
                    <el-button
                      v-for="acc in group.accounts"
                      :key="acc.username"
                      class="quick-btn"
                      size="small"
                      :type="group.color"
                      plain
                      :disabled="disabled || loading"
                      @click="onQuickLogin(acc.username)"
                    >
                      {{ acc.label }}
                    </el-button>
                  </div>
                </div>
              </div>
            </Motion>
          </el-form>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@import url("@/style/login.css");
</style>

<style lang="scss" scoped>
:deep(.el-input-group__append, .el-input-group__prepend) {
  padding: 0;
}

.quick-login {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.quick-group {
  display: flex;
  align-items: center;
  gap: 8px;

  .quick-group-title {
    flex-shrink: 0;
    width: 72px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    text-align: right;
  }

  .quick-group-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .quick-btn {
    padding: 5px 12px;
    margin: 0;
    font-size: 12px;
    border-radius: 4px;
  }
}
</style>
