<script setup lang="ts">
import { Connection, UserFilled } from "@element-plus/icons-vue";
import { reactive, ref, watch } from "vue";

import type { AgentSession } from "@/types";
import { normalizeSession } from "@/utils/session";

const props = defineProps<{
  modelValue: boolean;
  initialValue: AgentSession;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  confirm: [session: AgentSession];
}>();

const form = reactive<AgentSession>({ ...props.initialValue });
const validationError = ref("");

watch(
  () => props.initialValue,
  (value) => {
    Object.assign(form, value);
    validationError.value = "";
  },
  { deep: true },
);

function submit(): void {
  const normalized = normalizeSession(form);
  const missing = [
    ["会话 ID", normalized.conversation_id],
    ["租户 ID", normalized.tenant_id],
    ["调用方 ID", normalized.principal_id],
    ["调用方类型", normalized.principal_type],
  ].find(([, value]) => !value);
  if (missing) {
    validationError.value = `请填写${missing[0]}。`;
    return;
  }
  validationError.value = "";
  emit("confirm", normalized);
  emit("update:modelValue", false);
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    class="session-dialog"
    width="min(46rem, calc(100vw - 2rem))"
    align-center
    append-to-body
    :show-close="false"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
  >
    <template #header>
      <div class="session-dialog-heading">
        <span class="session-dialog-icon">
          <el-icon><Connection /></el-icon>
        </span>
        <div>
          <h2>创建临时会话</h2>
          <p>模拟企业应用传入的可信调用上下文。参数仅保存在当前标签页中。</p>
        </div>
      </div>
    </template>

    <el-form class="session-form" label-position="top" @submit.prevent="submit">
      <el-form-item class="session-form-wide" label="会话 ID" required>
        <el-input v-model="form.conversation_id" placeholder="例如：conversation-20260902" maxlength="255" />
      </el-form-item>
      <el-form-item label="租户 ID" required>
        <el-input v-model="form.tenant_id" placeholder="tenant_id" maxlength="64" />
      </el-form-item>
      <el-form-item label="调用方 ID" required>
        <el-input v-model="form.principal_id" placeholder="principal_id" maxlength="128">
          <template #prefix><el-icon><UserFilled /></el-icon></template>
        </el-input>
      </el-form-item>
      <el-form-item label="活动组织单元 ID（可选）">
        <el-input v-model="form.active_organization_unit_id" placeholder="留空表示租户级" maxlength="64" />
      </el-form-item>
      <el-form-item label="调用方类型" required>
        <el-input v-model="form.principal_type" placeholder="user" maxlength="32" />
      </el-form-item>
      <el-alert
        v-if="validationError"
        class="session-form-error"
        type="error"
        :closable="false"
        show-icon
        :title="validationError"
      />
    </el-form>

    <template #footer>
      <div class="session-dialog-footer">
        <span>会话由第一次发送消息时在服务端自动建立。</span>
        <el-button type="primary" @click="submit">开始对话</el-button>
      </div>
    </template>
  </el-dialog>
</template>
