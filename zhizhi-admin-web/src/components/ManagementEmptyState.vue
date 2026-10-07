<script setup lang="ts">
defineProps<{ title: string; description?: string }>();
</script>

<template>
  <el-empty class="management-empty-state" :description="title" :image-size="88">
    <p v-if="description" class="management-empty-description">{{ description }}</p>
    <slot />
  </el-empty>
</template>

<style scoped>
.management-empty-state {
  width: 100%;
  padding: 32px 16px;
}

.management-empty-state :deep(.el-empty__description p) {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.management-empty-state :deep(.el-empty__bottom) {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
}

.management-empty-description {
  min-height: 40px;
  max-width: 360px;
  margin: 0;
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 20px;
}

.management-empty-state :deep(.el-button) {
  height: 32px;
  font-size: 13px;
}
</style>
