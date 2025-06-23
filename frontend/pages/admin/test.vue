<script setup lang="ts">
import { onMounted } from 'vue'
import CircleCheck from '~icons/tabler/circle-check' // <-- Impor virtual module

onMounted(() => {
  console.log('Iconify Virtual Module Test:', CircleCheck)
})
</script>

<template>
  <div>
    <h3>Test Icons</h3>
    <VIcon icon="tabler:circle-check" size="x-large" />
    <p>Icon "tabler:circle-check" should be above.</p>

    <VIcon icon="success" size="x-large" />
    <p>Icon "success" (tabler:circle-check alias) should be above.</p>

    <VIcon icon="mdi-circle-check" size="x-large" />
    <p>Icon "mdi-circle-check" should be above.</p>

    <span class="tabler-circle-check custom-icon" style="font-size: 48px;"></span>
    <p>Icon "tabler-circle-check" via span should be above.</p>
  </div>
</template>