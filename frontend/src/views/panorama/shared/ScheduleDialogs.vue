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
      :reschedulable="ui.detailReschedulable"
      @released="onReleased"
      @reschedule="actions.rescheduleFromDetail()"
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
    <el-dialog
      v-if="ui.rescheduleVisible"
      v-model="ui.rescheduleVisible"
      title="抢占改期"
      width="440px"
    >
      <el-form label-width="72px">
        <el-form-item label="原记录">
          <span class="biz-sub">{{ rescheduleSummary }}</span>
        </el-form-item>
        <el-form-item label="新日期">
          <el-date-picker
            v-model="ui.rescheduleDate"
            type="date"
            value-format="YYYY-MM-DD"
            :disabled-date="disabledDate"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="时段">
          <el-select v-model="ui.rescheduleTemplateId" style="width: 100%">
            <el-option
              v-for="t in ui.rescheduleTemplates"
              :key="t.id"
              :label="`${t.name}（${t.start_time}-${t.end_time}）`"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <p class="biz-tip">
        「日期 +
        时段」的唯一占用仍然生效：目标时段已被他人抢占时会提示冲突，请重选。
      </p>
      <template #footer>
        <el-button @click="ui.rescheduleVisible = false">取消</el-button>
        <!-- :loading 防双击并发 PATCH（第二个大概率 40904 误报冲突，R4-F11） -->
        <el-button
          type="primary"
          :loading="ui.rescheduling"
          @click="actions.confirmReschedule()"
        >
          确定改期
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import dayjs from "dayjs";
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
  // 先作废策略详情缓存再刷新：否则保存后重开编辑弹窗仍用旧缓存预填（R4-F1/F-H1）
  actions.invalidateStrategyCache();
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

/** 改期弹窗顶部的原记录对照文案 */
const rescheduleSummary = computed(() => {
  const e = ui.rescheduleEvent;
  if (!e) return "";
  const booking = e.raw.type === "slot" ? e.raw.data.booking : null;
  return `${e.date} ${e.time}-${e.endTime} · ${e.title}${
    booking ? ` · ${booking.user_name}` : ""
  }`;
});

/** 只允许「今天 ~ 可抢窗口截止日」（与后端校验同口径，少一次失败往返） */
function disabledDate(value: Date) {
  const day = dayjs(value);
  if (day.isBefore(dayjs().startOf("day"))) return true;
  return (
    !!ui.rescheduleHorizonEnd && day.isAfter(dayjs(ui.rescheduleHorizonEnd))
  );
}
</script>
