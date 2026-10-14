<script setup lang="ts">
// 系统管理 - 策略模板 Tab：模板 CRUD（列表数据由父组件持有，操作后通知刷新）
import { reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { adminApi } from "@/api/admin";
import type { TemplateItem } from "@/api/types";

defineOptions({ name: "AdminTemplatesTab" });

const props = defineProps<{
  templates: TemplateItem[];
}>();

const emit = defineEmits<{ refresh: [] }>();

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

/** 模板弹窗保存请求进行中（按钮 :loading 防双击重复提交，对齐 VersionsTab 范式，R4-F3） */
const savingTemplate = ref(false);

async function saveTemplate() {
  if (!templateForm.name) {
    ElMessage.warning("请输入模板名称");
    return;
  }
  // 在途守卫：并发第二次 create 会撞 40902 重名弹错（F-H3）
  if (savingTemplate.value) return;
  savingTemplate.value = true;
  try {
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
    emit("refresh");
  } catch {
    // 失败已由拦截器提示（如重名 40902），保留弹窗便于修改重试
  } finally {
    savingTemplate.value = false;
  }
}

async function deleteTemplate(t: TemplateItem) {
  try {
    await ElMessageBox.confirm(
      `确认删除模板「${t.name}」？被策略引用的模板不可删除。`,
      "删除模板",
      {
        type: "warning",
        confirmButtonText: "确认删除",
        cancelButtonText: "取消"
      }
    );
  } catch {
    return; // 用户取消
  }
  try {
    await adminApi.deleteTemplate(t.id);
  } catch {
    return; // 失败已由拦截器提示（如 40903 被策略引用）
  }
  ElMessage.success("模板已删除");
  emit("refresh");
}
</script>

<template>
  <div>
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
          <el-button
            type="primary"
            link
            size="small"
            @click="openTemplateDialog(row as TemplateItem)"
            >编辑</el-button
          >
          <el-button
            type="danger"
            link
            size="small"
            @click="deleteTemplate(row as TemplateItem)"
            >删除</el-button
          >
        </template>
      </el-table-column>
    </el-table>

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
          <el-input
            v-model="templateForm.description"
            type="textarea"
            :rows="2"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="templateDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="savingTemplate"
          @click="saveTemplate"
          >保存</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  margin-bottom: 12px;
}
</style>
