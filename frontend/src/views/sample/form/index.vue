<!-- 示例菜单 · 表单录入 /sample/form -->
<!-- 定位：占位演示页。展示带校验规则的标准表单区块（提交仅本地提示，不发请求） -->
<template>
  <div class="biz-page">
    <div class="biz-card form-card">
      <div class="biz-card-head">
        <span class="biz-card-title">示例录入表单</span>
        <span class="biz-sub">演示 el-form 校验骨架</span>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="88px">
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
        <el-form-item label="备注">
          <el-input
            v-model="form.remark"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="选填"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="submit">提交</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
      <p class="biz-tip">
        示例页不发送任何请求；「提交」仅演示校验通过与重置流程。
      </p>
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
.form-card {
  max-width: 560px;
}
</style>
