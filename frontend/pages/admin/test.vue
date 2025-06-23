<script setup lang="ts">
import { onMounted } from 'vue'
import CircleCheck from '~icons/tabler/circle-check' // <-- Biarkan ini

onMounted(() => {
  console.log('Iconify Virtual Module Test:', CircleCheck) // <-- Biarkan ini
})
</script>

<template>
  <div>
    <h3>Tes Render Langsung</h3>
    <p>Ikon di bawah ini dirender langsung (seharusnya muncul):</p>
    <CircleCheck style="font-size: 48px; color: limegreen;" />
    <hr style="margin: 2rem 0;">


    <h3>Test Icons Asli (via VIcon)</h3>
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