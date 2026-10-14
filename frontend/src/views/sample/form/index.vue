<!-- 示例菜单 · 表单录入 /sample/form -->
<!-- 定位：占位演示页。双列紧凑表单（短字段并排，备注整行），提交仅本地提示，不发请求 -->
<!-- 紧凑口径：说明性文案收进卡片头一行副标题，页面底部不再堆提示段落 -->
<template>
  <div class="biz-page">
    <div class="biz-card biz-card-compact form-card">
      <div class="biz-card-head">
        <span class="biz-card-title">示例录入表单</span>
        <span class="biz-sub">校验演示，不发送请求</span>
      </div>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="72px"
        class="form-grid"
      >
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="2~20 个字符" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" placeholder="请选择角色">
            <el-option
              v-for="r in roleOptions"
              :key="r"
              :label="r"
              :value="r"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="name@example.com" />
        </el-form-item>
        <el-form-item label="接收通知">
          <el-switch v-model="form.notify" />
        </el-form-item>
        <el-form-item label="备注" class="span-full">
          <el-input
            v-model="form.remark"
            type="textarea"
            :rows="2"
            maxlength="200"
            show-word-limit
            placeholder="选填"
          />
        </el-form-item>
      </el-form>
      <div class="form-actions">
        <el-button type="primary" size="small" @click="submit">提交</el-button>
        <el-button size="small" @click="reset">重置</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import {
  DEMO_FORM_INITIAL,
  DEMO_ROLE_OPTIONS,
  type DemoFormModel
} from "../demoData";

defineOptions({ name: "SampleForm" });

const roleOptions = DEMO_ROLE_OPTIONS;
const formRef = ref<FormInstance>();
const form = reactive<DemoFormModel>({ ...DEMO_FORM_INITIAL });

const rules: FormRules<DemoFormModel> = {
  name: [
    { required: true, message: "请输入名称", trigger: "blur" },
    { min: 2, max: 20, message: "长度应为 2~20 个字符", trigger: "blur" }
  ],
  role: [{ required: true, message: "请选择角色", trigger: "change" }],
  email: [{ type: "email", message: "邮箱格式不正确", trigger: "blur" }]
};

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  ElMessage.success("校验通过（示例页未发送请求）");
}

function reset() {
  Object.assign(form, DEMO_FORM_INITIAL);
  formRef.value?.clearValidate();
}
</script>

<style scoped lang="scss">
/* 双列栅格：短字段并排，长字段整行，收紧表单项下间距 */
.form-card {
  max-width: 640px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 16px;

  :deep(.el-form-item) {
    margin-bottom: 14px;
  }

  .span-full {
    grid-column: 1 / -1;
  }
}

.form-actions {
  display: flex;
  gap: 8px;
  margin-top: 2px;
}
</style>
