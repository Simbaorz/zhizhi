<script setup lang="ts">
defineProps<{
  title: string;
  body: string;
}>();
</script>

<template>
  <div class="flex min-h-56 items-center justify-center px-6 py-10 text-center">
    <div class="max-w-md">
      <h3 class="text-base font-semibold text-primary-text">{{ title }}</h3>
      <p class="mt-2 text-sm leading-6 text-secondary-text">{{ body }}</p>
    </div>
  </div>
</template>
