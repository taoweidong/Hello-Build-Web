<!-- 调度全景共用弹窗组：复用既有弹窗组件，布局层只放这一个标签 -->
<!-- 编排逻辑在 useScheduleActions，本组件只做显隐绑定与事件回接 -->
<template>
  <div>
    <WeeklyNewStrategyEditDialog
      v-if="ui.editVisible"
      v-model="ui.editVisible"
      :strategy="ui.editStrategy"
      :branches="ui.editBranches"
      @saved="onSaved"
    />
    <WeeklyNewStrategyBorrowDialog
      v-if="ui.borrowVisible"
      v-model="ui.borrowVisible"
      :strategy="ui.borrowStrategy"
      :current-version-id="ui.borrowVersionId"
    />
    <SlotBookingDialog
      v-if="ui.occupyVisible"
      v-model="ui.occupyVisible"
      :date="ui.occupyDate"
      :template="ui.occupyTemplate"
      :horizon-end="ui.occupyHorizonEnd"
      @booked="onBooked"
    />
    <SlotDetailDialog
      v-if="ui.detailVisible"
      v-model="ui.detailVisible"
      :date="ui.detailDate"
      :entry="ui.detailEntry"
      :template="ui.detailTemplate"
      @released="onReleased"
    />
    <BorrowApprovalDrawer
      v-if="ui.approvalVisible"
      v-model="ui.approvalVisible"
      :flows="borrowFlows"
    />
    <MyBookingsDrawer
      v-if="ui.myBookingsVisible"
      v-model="ui.myBookingsVisible"
      @changed="onBookingsChanged"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { ElMessage } from "element-plus";
import StrategyEditDialog from "@/views/weekly-new/components/StrategyEditDialog.vue";
import StrategyBorrowDialog from "@/views/weekly-new/components/StrategyBorrowDialog.vue";
import BookingDialog from "@/views/slot-booking/components/BookingDialog.vue";
import SlotDetailDialog from "@/views/slot-booking/components/SlotDetailDialog.vue";
import MyBookingsDrawer from "@/views/slot-booking/components/MyBookingsDrawer.vue";
import BorrowApprovalDrawer from "./BorrowApprovalDrawer.vue";
import { usePanorama } from "../context";

defineOptions({ name: "PanoramaScheduleDialogs" });

const { data, actions } = usePanorama();
const ui = actions.ui;

const borrowFlows = computed(() =>
  data.events.value.filter(e => e.source === "borrow")
);

async function onSaved() {
  await data.refresh();
}

async function onBooked() {
  await data.refresh();
}

async function onReleased() {
  await data.refresh();
}

async function onBookingsChanged() {
  await data.refresh();
}
</script>
