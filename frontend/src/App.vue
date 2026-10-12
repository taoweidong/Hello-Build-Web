<template>
  <el-config-provider :locale="currentLocale">
    <router-view />
    <ReDialog />
  </el-config-provider>
</template>

<script lang="ts">
import { defineComponent } from "vue";
import { ElConfigProvider } from "element-plus";
import { ReDialog } from "@/components/ReDialog";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import { refreshBusinessUser } from "@/utils/identity";

export default defineComponent({
  name: "app",
  components: {
    [ElConfigProvider.name]: ElConfigProvider,
    ReDialog
  },
  computed: {
    currentLocale() {
      return zhCn;
    }
  },
  mounted() {
    // 启动时静默刷新业务身份快照（角色/绑定版本服务端变更后无需重新登录即可感知）
    refreshBusinessUser();
  }
});
</script>
